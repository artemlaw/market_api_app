import logging

from market_api_app.utils import date_to_utc
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Ozon')


# Константа можно вынести в перспективе в файл настроек модуля
SORTING = 20.0  # Стоимость обработки, зависит от склада сдачи
ACQUIRING_PERCENT = 1.5  # Эквайринг, %
# Проверять актуальность тарифа по логистике в calculate_logistic_cost
# и Последней мили в calculate_last_mile_cost


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


def get_oz_orders(oz_client: Ozon, from_date='12-12-2024', to_date='13-12-2024'):
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
        return 76 + (liters - 1) * 12
    else:
        return 2344


def calculate_last_mile_cost(price: float) -> float:
    """
    Считает стоимость последней мили как 5.5% от цены, но не более 500 рублей.
    """
    cost = price * 5.5 / 100
    return min(cost, 500)


def get_oz_data_for_order(order: dict, tariffs_dict: dict, plan_margin: float = 28.0):
    margin = plan_margin / 100
    article = order.get('article', '')
    article_data = tariffs_dict[article]
    price = order.get("price", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)
    # TODO: Продолжить тут подбор значений
    commission_percent = round(article_data.get("FEE", {}).get("percent", 0.0) / 100, 3)
    commission_cost = round(price * commission_percent, 1)
    agency_commission = article_data.get("AGENCY_COMMISSION", 0.0)

    payment_percent = round(
        article_data.get("PAYMENT_TRANSFER", {}).get("percent", 0.0) / 100, 3
    )

    acquiring_cost = round((price * payment_percent) + agency_commission, 1)

    delivery_cost_percent = round(
        article_data.get("DELIVERY_TO_CUSTOMER", {}).get("percent", 0.0) / 100, 3
    )

    express_delivery_percent = round(
        article_data.get("EXPRESS_DELIVERY", {}).get("percent", 0.0) / 100, 3
    )

    delivery_percent = round(delivery_cost_percent + express_delivery_percent, 3)

    delivery_cross_cost = article_data.get("CROSSREGIONAL_DELIVERY", 0.0)
    sorting = SORTING

    recommended_price = round(
        (prime_cost + agency_commission + delivery_cross_cost + sorting)
        / (1 - margin - commission_percent - payment_percent - delivery_percent)
    )

    delivery_cost_max = article_data.get("DELIVERY_TO_CUSTOMER", {}).get(
        "max_value", 0.0
    )
    express_delivery_max = article_data.get("EXPRESS_DELIVERY", {}).get(
        "max_value", 0.0
    )
    express_delivery_min = article_data.get("EXPRESS_DELIVERY", {}).get(
        "min_value", 0.0
    )

    fbs_delivery, express_delivery = 0.0, 0.0
    if delivery_cost_max:
        fbs_delivery = min(round(price * delivery_percent, 1), delivery_cost_max)
        delivery_cost_ = min(
            recommended_price * delivery_cost_percent, delivery_cost_max
        )
        recommended_price = round(
            (prime_cost + agency_commission + delivery_cross_cost + sorting + delivery_cost_)
            / (1 - margin - commission_percent - payment_percent)
        )
    elif express_delivery_max:
        express_delivery = max(
            min(round(price * express_delivery_percent, 1), express_delivery_max),
            express_delivery_min,
        )
        express_delivery_ = max(
            min(recommended_price * express_delivery_percent, express_delivery_max),
            express_delivery_min,
        )
        recommended_price = round(
            (prime_cost + agency_commission + delivery_cross_cost + sorting + express_delivery_)
            / (1 - margin - commission_percent - payment_percent)
        )

    delivery_cost = fbs_delivery + express_delivery

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
