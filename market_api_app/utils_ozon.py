import logging
import math

from market_api_app import Ozon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Ozon Utils')

'''
Константа можно вынести в перспективе в файл настроек модуля
Необходимо проверять актуальность тарифов:
    * Логистика - calculate_logistic_cost
    * Последняя миля - calculate_last_mile_cost
'''
SORTING = 20.0  # Стоимость обработки, зависит от склада сдачи, ₽
LAST_MILE_PERCENT = 5.5  # Последняя миля, %
LAST_MILE_MAX = 500.0
ACQUIRING_PERCENT = 1.0  # Эквайринг, %
ACQUIRING_NDS = 1.22  # Эквайринг НДС22, %
ACQUIRING_PERCENT_NDS = ACQUIRING_PERCENT * ACQUIRING_NDS
MIN_PRICE = 60.0  # Минимальная рекомендуемая цена, ₽


def print_oz_constants():
    print('Предопределены значения:')
    print(f'* Эквайринг + НДС - {ACQUIRING_PERCENT_NDS}%')
    print(f'* Обработка - {SORTING}₽')
    print(f'* Минимальная рекомендуемая цена - {MIN_PRICE}₽')


def calculate_recommended_price_oz(prime_cost: float, delivery_cost: float, sorting: float, delivery_cross_cost: float,
                                   plan_margin: float, commission: float, acquiring: float, min_price: float) -> float:
    # Преобразуем проценты в доли
    plan_margin /= 100
    acquiring /= 100
    commission /= 100
    recom_price = round((prime_cost + delivery_cost + sorting + delivery_cross_cost)
                        / (1 - plan_margin - commission - acquiring), 0)
    if recom_price < min_price:
        recom_price = min_price
    return recom_price


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


def get_logistic_msk_ekb(price: float, liters: float) -> float:
    # Таблица в виде списка кортежей (min_vol, max_vol, price_le_300, price_gt_300)
    # Тариф для логистики Москва - Екатеринбург
    tariff_table = [
        (0.200, 17.28, 68.00),
        (0.400, 19.32, 76.00),
        (0.600, 21.35, 81.00),
        (0.800, 22.37, 81.00),
        (1.000, 23.38, 81.00),
        (1.250, 25.42, 87.00),
        (1.500, 26.43, 94.00),
        (1.750, 27.45, 94.00),
        (2.000, 29.48, 94.00),
        (3.000, 31.52, 96.00),
        (4.000, 35.58, 118.00),
        (5.000, 38.63, 141.00),
        (6.000, 42.70, 141.00),
        (7.000, 57.95, 162.00),
        (8.000, 62.02, 167.00),
        (9.000, 65.07, 169.00),
        (10.000, 69.13, 169.00),
        (11.000, 79.30, 181.00),
        (12.000, 83.37, 181.00),
        (13.000, 87.43, 182.00),
        (14.000, 92.52, 191.00),
        (15.000, 96.58, 211.00),
        (17.000, 96.58, 228.00),
        (20.000, 110.82, 253.00),
        (25.000, 118.95, 296.00),
        (30.000, 131.15, 345.00),
        (35.000, 146.40, 391.00),
        (40.000, 156.57, 436.00),
        (45.000, 175.88, 492.00),
        (50.000, 189.10, 532.00),
        (60.000, 207.40, 575.00),
        (70.000, 230.78, 664.00),
        (80.000, 249.08, 788.00),
        (90.000, 274.50, 891.00),
        (100.000, 284.67, 1000.00),
        (125.000, 331.43, 1129.00),
        (150.000, 381.25, 1357.00),
        (175.000, 436.15, 1532.00),
        (200.000, 483.93, 1861.00),
        (400.000, 805.20, 2939.00),
        (600.000, 805.20, 4240.00),
        (800.000, 805.20, 5533.00),
        (float('inf'), 805.20, 6718.00)
    ]
    # Поиск индекса соответствующему liters
    left, right = 0, len(tariff_table) - 1
    while left < right:
        mid = (left + right) // 2
        if liters <= tariff_table[mid][0]:
            right = mid
        else:
            left = mid + 1

    _, cost_low, cost_high = tariff_table[left]
    return cost_low if price <= 300 else cost_high


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
    acquiring_cost - Эквайринг 1% от цены + 22% НДС от суммы эквайринга
    delivery_cost - Логистика:
        * от 1,001 до 2 литров включительно — 99,64 ₽;
        * от 2,001 до 3 литров включительно — 117,94 ₽;
        * до 190 литров включительно — 23,39 ₽ за каждый дополнительный литр свыше 3 л;
        * от 190,001 до 1000 литров включительно — 6,1 ₽ за каждый дополнительный литр свыше 190 литров;
        * свыше 1000 литров — фиксированная стоимость 9432,87 ₽
    delivery_cross_cost - Доставка до места выдачи в РФ до 25р (было Последняя миля - 5,5% от цены, но не больше 500 р)
    sorting - Обработка = 20₽
    """
    article = order.get('article', '')
    article_data = tariffs_dict[article]
    price = order.get("price", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)

    sales_percent_fbs = article_data.get("sales_percent_fbs", 0)
    commission_percent = round(sales_percent_fbs / 100, 3)
    commission_cost = round(price * commission_percent, 1)

    payment_percent = round(ACQUIRING_PERCENT_NDS / 100, 3)
    # Можно сделать как в рекомендуемых ценах из article_data.get("acquiring", 0.0) * ACQUIRING_NDS, а не предопределенное
    acquiring_cost = round(price * payment_percent, 1)

    # Логистика
    delivery_cost = float(article_data.get("fbs_direct_flow_trans_max_amount", 0))
    # Доставка до места выдачи
    delivery_cross_cost = float(article_data.get("fbs_deliv_to_customer_amount", 0))
    # Обработка
    sorting = SORTING
    # Рекомендуемая цена
    recommended_price = calculate_recommended_price_oz(prime_cost, delivery_cost, sorting, delivery_cross_cost,
                                                       plan_margin, sales_percent_fbs, ACQUIRING_PERCENT_NDS, MIN_PRICE)
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


def get_oz_data_for_article(article: str, tariffs_dict: dict, plan_margin: float = 28.0):
    article_data = tariffs_dict[article]
    price = article_data.get("price", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)

    sales_percent_fbs = article_data.get("sales_percent_fbs", 0)
    commission_percent = round(sales_percent_fbs / 100, 3)
    commission_cost = round(price * commission_percent, 1)

    # payment_percent = round(ACQUIRING_PERCENT / 100, 3)
    # acquiring_cost = round(price * payment_percent * ACQUIRING_NDS, 1)
    acquiring_cost = round(article_data.get("acquiring", 0.0) * ACQUIRING_NDS, 1)

    # Логистика
    delivery_cost = float(article_data.get("fbs_direct_flow_trans_max_amount", 0))
    # Доставка до места выдачи
    delivery_cross_cost = float(article_data.get("fbs_deliv_to_customer_amount", 0))
    # Обработка
    sorting = SORTING
    # Рекомендуемая цена
    recommended_price = calculate_recommended_price_oz(prime_cost, delivery_cost, sorting, delivery_cross_cost,
                                                       plan_margin, sales_percent_fbs, ACQUIRING_PERCENT_NDS, MIN_PRICE)
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
