import time
from market_api_app import WB
from market_api_app.utils import get_date_for_request
from market_api_app.utils_ms import get_attributes_dict, get_volume


def find_warehouse_by_name(warehouses: list, name: str) -> dict | None:
    return next((warehouse for warehouse in warehouses if warehouse['warehouseName'] == name), None)


def get_logistic_dict(tariffs_data: dict, warehouse_name: str = 'Маркетплейс') -> dict:
    tariff = find_warehouse_by_name(warehouses=tariffs_data['response']['data']['warehouseList'], name=warehouse_name)
    if not tariff:
        tariff = find_warehouse_by_name(warehouses=tariffs_data['response']['data']['warehouseList'], name='Коледино')
    # Логистика
    logistic_dict = {
        'KTR': 1.0,
        'TARIFF_FOR_BASE_L': float(tariff['boxDeliveryBase'].replace(',', '.')),
        'TARIFF_BASE': 1.0,
        'TARIFF_OVER_BASE': float(tariff['boxDeliveryLiter'].replace(',', '.')),
        'WH_COEFFICIENT': round(float(tariff['boxDeliveryAndStorageExpr'].replace(',', '.')) / 100, 2)
    }
    return logistic_dict


def get_category_dict(wb_client: WB) -> dict:
    commission = wb_client.get_commission()
    return {comm['subjectName']: (comm['kgvpMarketplace'], comm['paidStorageKgvp']) for comm in commission['report']}


def get_price_dict(wb_client: WB) -> dict:
    product_prices = wb_client.get_product_prices()
    # Если несколько размеров, то берет максимальную цену и дисконт
    price_dict = {d['nmID']: {
        'price': max(s['discountedPrice'] for s in d['sizes']),
        'discount': d['discount']
    } for d in product_prices}

    return price_dict


def create_prices_dict(prices_list: list) -> dict:
    prices_dict = {}
    for price in prices_list:
        name = price['priceType']['name']
        value = price['value']
        prices_dict[name] = value
    return prices_dict


# TODO: WB - Проверять на актуальность расчет логистики
def get_logistics(ktr: float, tariff_for_base_l: float, tariff_base: float, tariff_over_base: float,
                  wh_coefficient: float, volume: float) -> float:
    volume_calc = max(volume - tariff_base, 0)
    # Коэффициент логистики склада wh_coefficient стал в показателях уже применен
    wh_coefficient = 1.0
    logistics = round((tariff_for_base_l * tariff_base + tariff_over_base * volume_calc) * wh_coefficient * ktr, 2)
    return logistics


# TODO: WB - Проверять на актуальность расчет рекомендуемой цены
def calculate_recommended_price(prime_cost: float, logistics: float, plan_margin: float,
                                commission: float, acquiring: float = 1.6, min_price: float = 60.0) -> float:
    # Преобразуем проценты в доли
    plan_margin /= 100
    acquiring /= 100
    commission /= 100
    recom_price = round((prime_cost + logistics) / (1 - plan_margin - commission - acquiring), 0)
    if recom_price < min_price:
        recom_price = min_price
    return recom_price


def get_wb_data_for_article(nm_id: int, product: dict, prices_dict: dict, category_dict: dict, logistic_dict: dict,
                            plan_margin, acquiring: float = 1.5, fbs: bool = True, card_stocks: bool = False) -> dict:
    price = float(prices_dict.get('price', 0))
    discount = float(prices_dict.get('discount', 0))
    prime_cost = product.get('PRIME_COST', 0.0)
    category = product.get('CATEGORY', '')
    volume = product.get('VOLUME', 0.0)

    commissions = category_dict.get(category)
    if not commissions:
        print(
            f"У товара {nm_id} не заполнена категория или категория'{category}' отсутствует в словаре,"
            f" необходимо обновить данные в Мой склад")
        commission = 30.0
    else:
        commission = commissions[0] if fbs else commissions[1]

    logistics = get_logistics(logistic_dict['KTR'], logistic_dict['TARIFF_FOR_BASE_L'], logistic_dict['TARIFF_BASE'],
                              logistic_dict['TARIFF_OVER_BASE'], logistic_dict['WH_COEFFICIENT'], volume)

    commission_cost = round(commission / 100 * price, 1)
    acquiring_cost = round(acquiring / 100 * price, 1)

    reward = round(commission_cost + acquiring_cost + logistics, 1)
    profit = round(price - prime_cost - reward, 1)
    profitability = round(profit / price * 100, 1)

    recommended_price = calculate_recommended_price(prime_cost, logistics, plan_margin, commission, acquiring)

    data = {
        'name': product.get('NAME', ''),
        'article': product.get('ARTICLE', ''),
        'nm_id': nm_id,
        'url': f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx',
        'stock': product.get('STOCK', 0.0),
        'discount': discount,
        'price': price,
        'recommended_price': recommended_price,
        'prime_cost': prime_cost,
        'commission': commission_cost,
        'acquiring': acquiring_cost,
        'logistics': logistics,
        'profit': profit,
        'profitability': profitability
    }
    if card_stocks:
        data = {
            'name': product.get('NAME', ''),
            'article': product.get('ARTICLE', ''),
            'nm_id': nm_id,
            'url': f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx',
            'stock': product.get('STOCK', 0.0),
            'stock_fbs': product.get('STOCK_FBS', 0),
            'stock_fbo': product.get('STOCK_FBO', 0),
            'discount': discount,
            'price': price,
            'recommended_price': recommended_price,
            'prime_cost': prime_cost,
            'commission': commission_cost,
            'acquiring': acquiring_cost,
            'logistics': logistics,
            'profit': profit,
            'profitability': profitability
        }

    return data


def get_order_data(order: dict, product: dict, base_dict: dict, acquiring: float = 1.5, fbs: bool = True) -> dict:
    wb_prices_dict = base_dict['wb_prices_dict']
    if fbs:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'], warehouse_name='Маркетплейс')
    else:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'],
                                          warehouse_name=order.get('warehouseName', 'Коледино'))

    nm_id = order.get('nmId', '')
    sale_prices = product.get('salePrices', [])
    prices_dict = create_prices_dict(sale_prices)

    # Получение цены
    price = wb_prices_dict.get(nm_id, {}).get('price')
    if not price:
        price = prices_dict.get('Цена WB после скидки', 0) / 100

    # Получение скидки
    discount = wb_prices_dict.get(nm_id, {}).get('discount')
    if not discount:
        price_before_discount = prices_dict.get('Цена WB до скидки', 0.0)
        price_after_discount = prices_dict.get('Цена WB после скидки', 0.0)
        if price_before_discount:
            discount = (1 - round(price_after_discount / price_before_discount, 1)) * 100
        else:
            discount = 0

    cost_price_c = prices_dict.get('Цена основная', 0.0)
    cost_price = cost_price_c / 100
    order_price = round(order.get('finishedPrice', 0.0), 1)

    attributes = product.get('attributes', [])
    attributes_dict = get_attributes_dict(attributes)
    volume = get_volume(attributes_dict)

    logistics = get_logistics(logistic_dict['KTR'], logistic_dict['TARIFF_FOR_BASE_L'], logistic_dict['TARIFF_BASE'],
                              logistic_dict['TARIFF_OVER_BASE'], logistic_dict['WH_COEFFICIENT'], volume)

    category = order.get('subject', attributes_dict["Категория товара"])

    commissions = base_dict.get('category_dict', {}).get(category)
    if not commissions:
        print('Не удалось определить комиссию по категории', category, 'по умолчанию указал 30%')
        commission = 30.0
    else:
        commission = commissions[0] if fbs else commissions[1]

    commission_cost = round(commission / 100 * price, 1)
    acquiring_cost = round(acquiring / 100 * price, 1)

    reward = round(commission_cost + acquiring_cost + logistics, 1)
    profit = round(price - cost_price - reward, 1)
    profitability = round(profit / price * 100, 1)

    order_commission_cost = round(commission / 100 * order_price, 1)
    order_acquiring_cost = round(acquiring / 100 * order_price, 1)

    order_reward = round(order_commission_cost + order_acquiring_cost + logistics, 1)
    order_profit = round(order_price - cost_price - order_reward, 1)
    order_profitability = round(order_profit / order_price * 100, 1)

    model = 'FBS_' if fbs else 'FBO_'

    data = {
        'name': product.get('name', ''),
        'nm_id': nm_id,
        'article': product.get('article', ''),
        'stock': base_dict.get('ms_stocks_dict', {}).get(nm_id, 0),
        'order_create': order.get('date', ''),
        'order_name': model + order.get('sticker', '0'),
        'quantity': 1,
        'discount': discount,
        'item_price': price,
        'order_price': order_price,
        'cost_price': cost_price,
        'commission': commission_cost,
        'acquiring': acquiring_cost,
        'logistics': logistics,
        'reward': reward,
        'profit': profit,
        'profitability': profitability,
        'order_reward': order_reward,
        'order_profit': order_profit,
        'order_profitability': order_profitability
    }

    return data


def wb_get_orders(wb_client: WB, start_of_day: str, end_of_day: str):
    fbo_tuple_from_date, from_date_for_fbs, to_date_for_fbs = get_date_for_request(start_of_day, end_of_day)
    wb_orders = []
    total_dates = len(fbo_tuple_from_date)
    for i, from_date in enumerate(fbo_tuple_from_date):
        wb_orders.extend(wb_client.get_orders(from_date))
        if i < total_dates - 1:
            time.sleep(20)

    # Запас +/- 3ч - 10800( 6ч - 21600)
    wb_orders_fbs = wb_client.get_orders_fbs(from_date=from_date_for_fbs - 10800, to_date=to_date_for_fbs + 10800)
    rids = {order_fbs.get('rid') for order_fbs in wb_orders_fbs}

    orders_fbs_cancel = []
    orders_fbo_cancel = []
    orders_fbs = []
    orders_fbo = []

    for order in wb_orders:
        srid = order.get('srid')
        order_type = order.get('orderType')
        is_cancel = order.get('isCancel')

        if order_type == 'Клиентский' and not is_cancel:
            if order.get('srid') in rids:
                orders_fbs.append(order)
            else:
                orders_fbo.append(order)
        else:
            if srid in rids:
                orders_fbs_cancel.append(order)
            else:
                orders_fbo_cancel.append(order)

    print(f"{'Модель':<15}{'Количество':<10}")
    print('-' * 25)
    print(f"{'FBS':<15}{len(orders_fbs):<10}")
    print(f"{'FBS отмены':<15}{len(orders_fbs_cancel):<10}")
    print(f"{'FBO':<15}{len(orders_fbo):<10}")
    print(f"{'FBO отмены':<15}{len(orders_fbo_cancel):<10}")
    print('-' * 25)
    print(f"{'Всего заказов':<15}{len(wb_orders):<10}")
    print(f"{'Без отмены':<15}{len(wb_orders) - len(orders_fbs_cancel) - len(orders_fbo_cancel):<10}")

    return orders_fbs, orders_fbo
