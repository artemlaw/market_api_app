import os
import time
from datetime import datetime, timedelta

from market_api_app import WB, MoySklad
from market_api_app.utils_ms import get_ms_stocks_dict


def get_api_tokens() -> (str, str):
    try:
        from google.colab import userdata
        MS_API_TOKEN = userdata.get("MS_API_TOKEN")
        WB_API_TOKEN = userdata.get("WB_API_TOKEN")
        YM_API_TOKEN = userdata.get("YM_API_TOKEN")
        OZ_CLIENT_ID = userdata.get("OZ_CLIENT_ID")
        OZ_API_TOKEN = userdata.get("OZ_API_TOKEN")
        return MS_API_TOKEN, WB_API_TOKEN, YM_API_TOKEN, OZ_CLIENT_ID, OZ_API_TOKEN
    except ImportError:
        pass
    from dotenv import load_dotenv

    load_dotenv()
    MS_API_TOKEN = os.getenv("MS_API_TOKEN")
    WB_API_TOKEN = os.getenv("WB_API_TOKEN")
    YM_API_TOKEN = os.getenv("YM_API_TOKEN")
    OZ_CLIENT_ID = os.getenv("OZ_CLIENT_ID")
    OZ_API_TOKEN = os.getenv("OZ_API_TOKEN")

    return MS_API_TOKEN, WB_API_TOKEN, YM_API_TOKEN, OZ_CLIENT_ID, OZ_API_TOKEN


def get_ya_ids():
    try:
        from google.colab import userdata

        fbs_campaign_id = userdata.get("YA_FBS_CAMPAIGN_ID")
        ex_campaign_id = userdata.get("YA_EXPRESS_CAMPAIGN_ID")
        business_id = userdata.get("YA_BUSINESS_ID")
        return fbs_campaign_id, ex_campaign_id, business_id
    except ImportError:
        pass
    from dotenv import load_dotenv

    load_dotenv()
    fbs_campaign_id = os.getenv("YA_FBS_CAMPAIGN_ID")
    ex_campaign_id = os.getenv("YA_EXPRESS_CAMPAIGN_ID")
    business_id = os.getenv("YA_BUSINESS_ID")

    return fbs_campaign_id, ex_campaign_id, business_id


def get_category_dict(wb_client: WB) -> dict:
    commission = wb_client.get_commission()
    return {comm['subjectName']: (comm['kgvpMarketplace'], comm['paidStorageKgvp']) for comm in commission['report']}


def get_price_dict(wb_client: WB) -> dict:
    data = wb_client.get_product_prices()
    # TODO: Добавить возможность получения данных по другим размерам, либо изменить источник
    price_dict = {d['nmID']: {'price': d['sizes'][0]['discountedPrice'], 'discount': d['discount']} for d in data
                  if len(d['sizes']) == 1}
    return price_dict


def get_dict_for_report(products: list, ms_client: MoySklad, wb_client: WB) -> dict:
    category_dict = get_category_dict(wb_client)
    tariffs_logistic_data = wb_client.get_tariffs_for_box()
    ms_stocks_dict = get_ms_stocks_dict(ms_client, products)
    wb_prices_dict = get_price_dict(wb_client)

    return {
        'ms_stocks_dict': ms_stocks_dict,
        'category_dict': category_dict,
        'tariffs_data': tariffs_logistic_data,
        'wb_prices_dict': wb_prices_dict
    }


def create_code_index(elements: list) -> dict:
    code_index = {}
    for element in elements:
        code = int(element.get('code'))
        if code:
            code_index[code] = element
    return code_index


def find_warehouse_by_name(warehouses: list, name: str) -> dict | None:
    return next((warehouse for warehouse in warehouses if warehouse['warehouseName'] == name), None)


def get_value_by_name(elements, name):
    return next((element["value"] for element in elements if element["name"] == name), None)


def get_logistic_dict(tariffs_data: dict, warehouse_name: str = 'Маркетплейс') -> dict:
    tariff = find_warehouse_by_name(tariffs_data['response']['data']['warehouseList'], warehouse_name)
    if not tariff:
        tariff = find_warehouse_by_name(tariffs_data['response']['data']['warehouseList'], 'Коледино')
    # Логистика
    logistic_dict = {
        'KTR': 1.0,
        'TARIFF_FOR_BASE_L': float(tariff['boxDeliveryBase'].replace(',', '.')),
        'TARIFF_BASE': 1.0,
        'TARIFF_OVER_BASE': float(tariff['boxDeliveryLiter'].replace(',', '.')),
        'WH_COEFFICIENT': round(float(tariff['boxDeliveryAndStorageExpr'].replace(',', '.')) / 100, 2)
    }
    return logistic_dict


def create_prices_dict(prices_list: list) -> dict:
    prices_dict = {}
    for price in prices_list:
        name = price['priceType']['name']
        value = price['value']
        prices_dict[name] = value
    return prices_dict


def create_attributes_dict(attributes_list: list) -> dict:
    attributes_dict = {}
    for attribute in attributes_list:
        name = attribute['name']
        value = attribute['value']
        attributes_dict[name] = value
    return attributes_dict


def get_product_volume(attributes_dict: dict) -> float:
    return ((attributes_dict.get('Длина', 0) * attributes_dict.get('Ширина', 0) * attributes_dict.get('Высота', 0))
            / 1000.0)


# TODO: Проверять на актуальность
def get_logistics(ktr: float, tariff_for_base_l: float, tariff_base: float, tariff_over_base: float,
                  wh_coefficient: float, volume: float) -> float:
    volume_calc = max(volume - tariff_base, 0)
    # Коэффициент логистики склада wh_coefficient стал в показателях уже применен
    wh_coefficient = 1.0
    logistics = round((tariff_for_base_l * tariff_base + tariff_over_base * volume_calc) * wh_coefficient * ktr, 2)
    return logistics


def get_order_data(order: dict, product: dict, base_dict: dict, acquiring: float = 1.5, fbs: bool = True) -> dict:
    wb_prices_dict = base_dict['wb_prices_dict']
    if fbs:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'], warehouse_name='Маркетплейс')
    else:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'], warehouse_name=order.get('warehouseName', 'Коледино'))

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
    attributes_dict = create_attributes_dict(attributes)
    volume = get_product_volume(attributes_dict)

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


def get_date_for_request(start_date_str: str, end_date_str: str) -> tuple[tuple, int, int]:
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    from_date_for_fbs = int(start_date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    if start_date == end_date:
        return (start_date_str,), from_date_for_fbs, int(
            start_date.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())

    from_date_for_fbo = tuple(
        (start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((end_date - start_date).days + 1))

    to_date_for_fbs = int(end_date.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())

    return from_date_for_fbo, from_date_for_fbs, to_date_for_fbs


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


def date_to_utc(date_str: str, start_of_day: bool = True) -> str:
    """
    Принимает строку в формате '15.12.2024' и возвращает строку в формате UTC: '2024-12-15T00:00:00Z'
    или '2024-12-15T23:59:59Z'
    """
    date_ = datetime.strptime(date_str, '%d-%m-%Y')
    if start_of_day:
        date_ = date_.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        date_ = date_.replace(hour=23, minute=59, second=59, microsecond=999999)
    return date_.isoformat() + 'Z'


def format_date(date_str: str) -> str:
    """
    Принимает дату в формате 'YYYY-MM-DD' и возвращает её в формате 'DD-MM-YYYY'
    """
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d-%m-%Y')


if __name__ == '__main__':
    dates = get_date_for_request('2024-08-30', '2024-09-01')
    print(dates)
