import logging
import math

from market_api_app.utils import date_to_utc
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Ozon')

'''
Константа можно вынести в перспективе в файл настроек модуля
Необходимо проверять актуальность тарифов:
    * Логистика - calculate_logistic_cost
    * Последняя миля - calculate_last_mile_cost
'''
SORTING = 20.0  # Стоимость обработки, зависит от склада сдачи
LAST_MILE_PERCENT = 5.5  # Последняя миля, %
LAST_MILE_MAX = 500.0
ACQUIRING_PERCENT = 1.6  # Эквайринг, %


class Ozon(ApiBase):
    def __init__(self, client_id: str, api_key: str, max_retries: int = 3, delay_seconds: int = 15):
        super().__init__(max_retries=max_retries, delay_seconds=delay_seconds)
        self.headers = {
            "Api-Key": api_key,
            "Client-Id": client_id,
            "Content-Type": "application/json",
        }
        self.host = "https://api-seller.ozon.ru/"

    def get_products_info(self, product_id: list):
        # logger.info(f"Получение детальной информации по товарам")
        url = self.host + "v2/product/info/list"
        data = {"product_id": product_id}
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по товарам.')
        return result_json.get("result", {}).get("items", [])

    def get_prices(self, product_id: list):
        logger.info(f"Получение данных по тарифам")
        url = self.host + "v4/product/info/prices"
        data = {
            "filter": {
                "product_id": product_id,
                "visibility": "ALL"
            },
            "last_id": "",
            "limit": 1000
        }
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по тарифам.')
        return result_json.get("result", {}).get("items", [])

    def get_products(self):
        logger.info(f"Получение данных по товарах")
        url = self.host + "v3/product/list"
        limit = 1000
        data = {
            "filter": {
                "offer_id": [],
                "product_id": [],
                "visibility": "ALL"
            },
            "last_id": "",
            "limit": limit
        }

        offers_list = []
        total = limit
        while True:
            result = self.post(url, data)
            result_json = result.json() if result else {}
            if result_json and result_json.get("result"):
                products_ = result_json.get("result", {}).get("items", [])
                products_ids = [product['product_id'] for product in products_ if not product['archived']]
                products_info = self.get_prices(product_id=products_ids)
                offers_list += products_info
                if result_json.get("result", {}).get("total", 0) < total:
                    break
                data["last_id"] = result_json.get("result", {}).get("last_id", "")
                total += limit
            else:
                logger.error("Не удалось получить данные о товарах.")
                break
        return offers_list

    def get_orders(self, from_date, to_date):
        logger.info(f"Получение информации о заказах")
        url = self.host + "v3/posting/fbs/list"
        since = date_to_utc(from_date)
        to = date_to_utc(to_date, start_of_day=False)
        data = {
            "dir": "ASC",
            "filter": {
                "is_quantum": False,
                "since": since,
                "to": to
            },
            "limit": 1000,
            "offset": 0,
            "with": {
                "analytics_data": False,
                "barcodes": False,
                "financial_data": True,
                "translit": False
            }
        }
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по заказам.')
        return result_json.get("result", {}).get("postings", [])


def get_oz_orders(oz_client: Ozon, from_date: str = '12-12-2024', to_date: str = '13-12-2024') -> list:
    """
    Получение заказов
    :param oz_client:
    :param from_date: Дата начала в формате DD-MM-YYYY
    :param to_date: Дата окончания в формате DD-MM-YYYY
    :return: Список заказов в разрезе позиций товаров
    """
    print('Ozon: Получение заказов')
    oz_orders = oz_client.get_orders(from_date, to_date)
    return [
        {
            'order_number': order.get('posting_number', ''),
            'created': order.get('in_process_at', ''),
            'article': position.get('offer_id', ''),
            'price': float(position.get('price', '0.0000')),
            'quantity': position.get('quantity', 0)
        }
        for order in oz_orders
        if order.get('status', '') not in ['cancelled']
        for position in order.get('products', [])
    ]


def calculate_logistic_cost(liters: float) -> float:
    """
    Считает логистику по объемному весу по условию:
    * до 0,4 литра включительно — 43 ₽;
    * свыше 0,4 литра до 1 литра включительно — 76 ₽;
    * до 190 литров включительно — 12 ₽ за каждый дополнительный литр свыше объёма 1 л;
    * свыше 190 литров — 2344 ₽.
    """
    if liters <= 0.4:
        return 43
    elif 0.4 < liters <= 1:
        return 76
    elif 1 < liters <= 190:
        return 76 + math.ceil((liters - 1)) * 12
    else:
        return 2344


def calculate_last_mile_cost(price: float) -> float:
    """
    Считает стоимость последней мили как LAST_MILE_PERCENT % от цены, но не более LAST_MILE_MAX рублей.
    """
    cost = round(price * LAST_MILE_PERCENT / 100, 1)
    return min(cost, LAST_MILE_MAX)


def search_new_price(price: float, profitability: float, plan_profitability: float, kkk: float) -> ():
    # Если рентабельность меньше плана, то цену увеличиваем, если больше - уменьшаем
    if profitability > plan_profitability:
        new_price = price - kkk
        kkk = max(kkk / 2, 1)
    elif profitability < plan_profitability:
        new_price = price + kkk
        kkk = max(kkk / 2, 1)
    else:
        new_price = price
    return new_price, kkk


def get_profitability_for_price(price: float, prime_cost: float, commission_percent: float, payment_percent: float,
                                delivery_cost: float, sorting: float) -> float:
    reward = round(
        (price * commission_percent)
        + (price * payment_percent)
        + delivery_cost
        + calculate_last_mile_cost(price)
        + sorting,
        1,
    )
    profit = round(price - prime_cost - reward, 1)
    return round(profit / price * 100, 1)


# Использовать для проверки
def get_recommended_price(price: float, profitability: float, plan_profitability: float, prime_cost: float,
                          commission_percent: float, payment_percent: float, delivery_cost: float,
                          sorting: float) -> ():
    kkk = 100
    prof_min, prof_max = plan_profitability - 0.1, plan_profitability + 0.1
    while profitability <= prof_min or profitability >= prof_max:
        price, kkk = search_new_price(price, profitability, plan_profitability, kkk)
        profitability = get_profitability_for_price(price, prime_cost, commission_percent, payment_percent,
                                                    delivery_cost, sorting)
    return round(price), round(profitability, 1)


def get_oz_data_for_order(order: dict, tariffs_dict: dict, plan_margin: float = 28.0):
    """
    Расчет прибыли озон
    _________________________________________________________
    commission_cost - Комиссия % от цены, по категории товара
    acquiring_cost - Эквайринг 1,5% от цены
    delivery_cost - Логистика:
        * до 0,4 литра включительно — 43₽;
        * свыше 0,4 литра до 1 литра включительно — 76₽;
        * до 190 литров включительно — 12₽ за каждый дополнительный литр свыше объёма 1 литра;
        * свыше 190 литров — 2344₽
    delivery_cross_cost - Последняя миля 5,5% от цены, но не больше 500 рублей
    sorting - Обработка = 20₽
    """
    margin = round(plan_margin / 100, 3)
    article = order.get('article', '')
    article_data = tariffs_dict[article]
    price = order.get("price", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)

    commission_percent = round(article_data.get("sales_percent_fbs", 0) / 100, 3)
    commission_cost = round(price * commission_percent, 1)

    payment_percent = round(ACQUIRING_PERCENT / 100, 3)
    acquiring_cost = round(price * payment_percent, 1)

    volume_weight = article_data.get("volume_weight", 0.0)
    delivery_cost = calculate_logistic_cost(volume_weight)

    delivery_cross_percent = round(LAST_MILE_PERCENT / 100, 3)
    delivery_cross_cost = calculate_last_mile_cost(price)

    sorting = SORTING

    recommended_price = round(
        (prime_cost + delivery_cost + sorting)
        / (1 - margin - commission_percent - payment_percent - delivery_cross_percent)
    )

    # Проверяем, что последняя миля не превышает 500руб и делаем пересчет рекомендуемой цены
    delivery_cross_cost_ = calculate_last_mile_cost(recommended_price)
    recommended_price = round(
        (prime_cost + delivery_cost + sorting + delivery_cross_cost_)
        / (1 - margin - commission_percent - payment_percent)
    )

    # TODO: Добавить проверку на прибыль по рекомендованной цене

    reward = round(
        commission_cost
        + acquiring_cost
        + delivery_cost
        + delivery_cross_cost
        + sorting,
        1,
    )
    profit = round(price - prime_cost - reward, 1)
    profitability = round(profit / price * 100, 1)

    return {
        "order_number": order.get("order_number", ""),
        "created": order.get("created", ""),
        "quantity": order.get("quantity", 0.0),
        "name": article_data.get("NAME", ""),
        "article": article,
        "stock": article_data.get("STOCK", 0.0),
        "price": price,
        "recommended_price": recommended_price,
        "prime_cost": prime_cost,
        "commission": commission_cost,
        "acquiring": acquiring_cost,
        "delivery": delivery_cost,
        "crossregional_delivery": delivery_cross_cost,
        "sorting": sorting,
        "profit": profit,
        "profitability": profitability,
    }
