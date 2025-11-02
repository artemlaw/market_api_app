import logging
import re
from typing import Literal

from market_api_app import MoySklad
from market_api_app.utils import get_current_datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MS Utils')


def get_product_id_from_url(url: str) -> str | None:
    pattern = r'/product/([0-9a-fA-F-]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    else:
        return None


def get_stock_for_bundle(stocks_dict: dict, product: dict) -> float:
    product_bundles = product['components']['rows']
    product_stock = 0.0
    for bundle in product_bundles:
        bundle_id = get_product_id_from_url(bundle['assortment']['meta']['href'])
        if bundle_id in stocks_dict:
            p_stock = stocks_dict[bundle_id] // bundle['quantity']
            if p_stock > product_stock:
                product_stock = p_stock
    return product_stock


def get_ms_stocks_dict(ms_client: MoySklad, products: list) -> dict:
    print('Получение остатков номенклатуры')
    stocks = ms_client.get_stock()
    stocks_dict = {stock['assortmentId']: stock['quantity'] for stock in stocks}
    wb_stocks_dict = {int(product['code']): get_stock_for_bundle(stocks_dict, product) for product in products}
    return wb_stocks_dict


def get_prime_cost(prices_list: list, price_name: str = "Цена продажи") -> float:
    return next(
        (
            price.get("value", 0.0) / 100
            for price in prices_list
            if price["priceType"]["name"] == price_name
        ),
        0.0,
    )


def get_ms_orders(client: MoySklad, from_date: str, to_date: str, project: str = 'Яндекс Маркет') -> list:
    # from_date и to_date в формате '2024-12-10 00:00:00.000'
    # project = 'Ozon' или 'Яндекс Маркет'
    filter_ = f'?filter=moment>{from_date};moment<{to_date};&order=name,desc&expand=positions.assortment,state,project'
    print('Мой склад: Получение заказов')
    ms_orders = client.get_orders(filter_)

    return [
        {
            'order_number': order.get('name', ''),
            'created': order.get('created', ''),
            'article': position.get('assortment', {}).get('article', ''),
            'price': position.get('price', 0.0) / 100,
            'quantity': position.get('quantity', 0.0)
        }
        for order in ms_orders
        if order.get('state', {}).get('name', '') not in ['Отменен'] and order.get('project', {}).get('name',
                                                                                                      '') == project
        for position in order.get('positions', {}).get('rows', [])
    ]


def get_attributes_dict(attributes_list: list) -> dict:
    return {attribute['name']: attribute['value'] for attribute in attributes_list}


def get_volume(attributes_dict: dict) -> float:
    return ((attributes_dict.get('Длина', 0) * attributes_dict.get('Ширина', 0) * attributes_dict.get('Высота', 0))
            / 1000.0) if attributes_dict else 0.0


def get_ms_products(client: MoySklad, project: str = 'ЯндексМаркет') -> dict:
    """
    Получение товаров по project - значения 'ЯндексМаркет', 'Озон', 'WB'
    """
    ms_products = client.get_bundles()
    print('Мой склад: Получение товаров')
    # Отбираем только по проекту
    products_for_project = [
        product for product in ms_products if project in product.get('pathName', '')
    ]
    print("Мой склад: Получение остатка по товарам")
    stocks = client.get_stock()
    ms_stocks = {stock["assortmentId"]: stock["quantity"] for stock in stocks}
    print("Мой склад: Получение себестоимости товара")

    if project == 'WB':
        product_key = 'code'
        price_name = "Цена основная"
    else:
        product_key = 'article'
        price_name = "Цена продажи"

    return {
        product[product_key]: {
            "STOCK": get_stock_for_bundle(ms_stocks, product),
            "PRIME_COST": get_prime_cost(product.get("salePrices", []), price_name),
            "NAME": product["name"],
            "ATTRIBUTES": get_attributes_dict(product.get('attributes', []))
        }
        for product in products_for_project
    }


def get_stocks_info(sizes: list) -> tuple:
    fbs_stock = 0
    fbo_stock = 0

    for size in sizes:
        stocks = size.get('stocks')
        for stock in stocks:
            wh_id = stock.get('wh')
            if wh_id == 119261 or wh_id == 302088:
                fbs_stock += stock.get('qty')
            else:
                fbo_stock += stock.get('qty')

    return fbs_stock, fbo_stock


def get_prices_info(sizes: list) -> dict:
    shop_price = 0
    basket_price = 0
    fbs_stock = 0
    fbo_stock = 0

    for size in sizes:
        price = size.get('price', {})
        shop_price = price.get('basic', 0) / 100
        basket_price = price.get('product', 0) / 100
        stocks = size.get('stocks')
        for stock in stocks:
            wh_id = stock.get('wh')
            if wh_id == 119261 or wh_id == 302088:
                fbs_stock += stock.get('qty')
            else:
                fbo_stock += stock.get('qty')

    return {'shop_price': shop_price, 'basket_price': basket_price, 'fbs_stock': fbs_stock, 'fbo_stock': fbo_stock}


def get_cards_details(client: MoySklad, nm_ids: str, dest: str = '-1257786') -> list:
    """
    Получение данных корзины
    'dest': '12358062' - Краснодар
    'dest': '-1257786' - Москва
    'dest': '123589409' - Екатеринбург
    'dest': '-364763' - Новосибирск
    'dest': '-2133462' - Казань
    'dest': '123589328' - Подольск
    """

    # url = 'https://card.wb.ru/cards/v4/detail'
    url = (f'https://u-card.wb.ru/cards/v4/detail?appType=1&curr=rub&dest={dest}&spp=30&hide_dtype=11&ab_testing=false'
           f'&ab_testing=false&lang=ru&nm={nm_ids}')

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;"
                  "q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1"
    }
    client.headers = headers
    client.delay_seconds = 20  # TODO: Определить оптимальное время
    # result = client.get(url=url, params=params)
    result = client.get(url=url)
    response_json = result.json() if result else {}

    if not result:
        print('Не удалось получить данные по корзине.')
    return response_json.get('products', [])


def get_warehouses(client: MoySklad) -> list:
    """Получение данных о складах"""
    url = 'https://static-basket-01.wb.ru/vol0/data/stores-data.json'
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'sec-ch-ua': '"Chromium";v="134", "Google Chrome";v="134", "Not:A-Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/134.0.0.0 Safari/537.36'
    }
    client.headers = headers
    result = client.get(url=url)
    response_json = result.json() if result else []
    if not result:
        print('Не удалось получить данные по корзине.')
    return response_json


def get_stocks_by_size(sizes: list, wh: dict) -> tuple:
    fbs_stock = 0
    fbo_stock = 0
    stock_list = []

    for size in sizes:
        stocks = size.get('stocks')
        for stock in stocks:
            wh_id = stock.get('wh')
            # Подольск 3 - 302088
            if wh_id == 119261 or wh_id == 302088:
                fbs_stock += stock.get('qty')
                stock_list.append({'FBS': stock.get('qty')})
            else:
                fbo_stock += stock.get('qty')
                stock_list.append({wh.get(wh_id, {}).get('name', 'FBO'): stock.get('qty')})

    return fbs_stock, fbo_stock, stock_list


def get_stocks_by_full_stocks(full_stocks: dict, wh: dict) -> tuple:
    fbs_stock = 0
    fbo_stock = 0
    stock_list = []

    for wh_id, stock, in full_stocks.items():
        # Подольск 3 - 302088
        if wh_id == 119261 or wh_id == 302088:
            fbs_stock += stock
            stock_list.append({'FBS': stock})
        else:
            fbo_stock += stock
            stock_list.append({wh.get(wh_id, {}).get('name', 'FBO'): stock})

    return fbs_stock, fbo_stock, stock_list


def get_stocks_wh(client: MoySklad, nm_list: list) -> dict:
    cards = get_cards(client, nm_list)
    offices = get_warehouses(client)
    warehouses = {warehouse['id']: warehouse for warehouse in offices}
    if not cards:
        print('Не удалось получить данные по корзине.')
        return {}
    return {str(card['id']): get_stocks_by_size(card['sizes'], warehouses) for card in cards}


def get_cards(client: MoySklad, nn_list: list, max_portion: int = 100) -> list:
    results = []
    for i in range(0, len(nn_list), max_portion):
        portion = ';'.join(map(str, nn_list[i:i + max_portion]))
        result = get_cards_details(client, portion)
        if result:
            results.extend(result)
    return results


def aggregate_stocks(card_data):
    stocks = {}
    for size in card_data.get('sizes', []):
        for stock in size.get('stocks', []):
            if (wh := stock.get('wh')) is not None:
                stocks[wh] = stocks.get(wh, 0) + stock.get('qty', 0)
    return stocks


def get_cards_by_dist(client: MoySklad, nn_list: list, max_portion: int = 100) -> dict:
    # ПВЗ дистанции
    # 'dest': '-1257786' - Москва
    # 'dest': '123589328' - Подольск
    # 'dest': '123585769' - Котовск
    # 'dest': '-4039473' - Волгоград
    # 'dest': '123589409' - Екатеринбург
    # 'dest': '12358283' - Воронеж
    # 'dest': '12358062' - Краснодар
    # 'dest': '-364763' - Новосибирск
    # 'dest': '123585553' - Невинномысск
    # 'dest': '-2133462' - Казань

    # TODO: WB - Добавить дополнительные точки в случае необходимости
    dest_tuple = ('-1257786', '123589328', '123585769', '-4039473', '123589409', '12358283', '12358062', '-364763',
                  '123585553', '-2133462')
    results = {}
    nn_list_len = len(nn_list)
    step = round(nn_list_len / max_portion * 10)
    logger.info(f'Количество запросов всего: {step}')

    for i in range(0, nn_list_len, max_portion):
        portion = ';'.join(map(str, nn_list[i:i + max_portion]))
        result_dict = {}

        for dest in dest_tuple:
            cards = get_cards_details(client, portion, dest)
            step = step - 1
            logger.info(f'Осталось запросов: {step}')
            if cards:
                if dest == '-1257786':
                    for card in cards:
                        card_copy = card.copy()
                        card_copy['full_stocks'] = aggregate_stocks(card_copy)
                        # Добавляем элемент в результат
                        if 'id' in card_copy:
                            result_dict[card_copy['id']] = card_copy
                else:
                    for card in cards:
                        card_copy = card.copy()
                        full_stocks = aggregate_stocks(card_copy)
                        if 'id' in card_copy:
                            prev_card_full_stocks = result_dict.get(card_copy['id'], {}).get('full_stocks', {})
                            if prev_card_full_stocks:
                                prev_card_full_stocks.update(full_stocks)
                            result_dict[card_copy['id']]['full_stocks'] = prev_card_full_stocks
        if result_dict:
            results.update(result_dict)
    return results


def get_cards_stocks(client: MoySklad, nn_list: list):
    print("WB: Получение остатка из корзины")
    cards = get_cards(client, [int(product['code']) for product in nn_list])
    if not cards:
        print('Не удалось получить данные по корзине.')
        return {}
    return {str(card['id']): get_stocks_info(card['sizes']) for card in cards}


def get_cards_prices(client: MoySklad, nn_list: list):
    print("WB: Получение цены из корзины")
    cards = get_cards(client, nn_list)
    if not cards:
        print('Не удалось получить данные по корзине.')
        return {}
    return {int(card['id']): {**get_prices_info(card['sizes']), 'category': card['subjectId']} for card in cards}


def get_stocks_wh_full(client: MoySklad, nm_list: list) -> dict:
    print("WB: Получение остатков из корзины")
    cards = get_cards_by_dist(client, nm_list)
    offices = get_warehouses(client)
    warehouses = {warehouse['id']: warehouse for warehouse in offices}
    if not cards:
        print('Не удалось получить данные по корзине.')
        return {}
    return {str(card_id): get_stocks_by_full_stocks(card['full_stocks'], warehouses) for card_id, card in cards.items()}


def get_ms_products_for_wb(client: MoySklad, fbo_stock: bool = False, limiter_list: list = None) -> dict:
    """
    Получение товаров по 'WB'
    """
    ms_products = client.get_bundles()
    print('Мой склад: Получение товаров')
    # Отбираем по лимитеру если есть
    if limiter_list:
        products_for_project = [product for product in ms_products if int(product['code']) in limiter_list]
    # Отбираем только по проекту
    else:
        products_for_project = [product for product in ms_products if product.get('pathName', '') == 'WB']

    print("Мой склад: Получение остатка по товарам")
    stocks = client.get_stock()
    ms_stocks = {stock["assortmentId"]: stock["quantity"] for stock in stocks}
    stock_from_basket = {}
    if fbo_stock:
        # Получить остаток FBO из корзины
        stock_from_basket = get_cards_stocks(client, products_for_project)

    print("Мой склад: Получение себестоимости товара")

    return {
        int(product_['code']): {
            "STOCK": get_stock_for_bundle(ms_stocks, product_),
            "STOCK_FBS": stock_from_basket.get(product_['code'], (0, 0))[0] if stock_from_basket else 0,
            "STOCK_FBO": stock_from_basket.get(product_['code'], (0, 0))[1] if stock_from_basket else 0,
            "PRIME_COST": get_prime_cost(product_.get('salePrices', []), 'Цена основная'),
            "NAME": product_['name'],
            "ARTICLE": product_.get('article', ''),
            "CATEGORY": get_attributes_dict(product_.get('attributes', [])).get('Категория товара', ''),
            "VOLUME": get_volume(get_attributes_dict(product_.get('attributes', [])))
        }
        for product_ in products_for_project
    }


def get_sales_by_orders(orders: list) -> dict:
    articles_quantities = {}
    for order in orders:
        positions = order.get('positions', {}).get('rows', [])
        for position in positions:
            article = position.get('assortment', {}).get('article', '')
            quantity = position.get('quantity', 0.0)
            if article in articles_quantities:
                articles_quantities[article] += quantity
            else:
                articles_quantities[article] = quantity
    return articles_quantities


def change_stock(ms_client: MoySklad, org_id: str, store_id: str, project_id: str, positions: list,
                 change_type: Literal['add', 'remove'] = 'add') -> dict:
    """
    change_type: 'add' or 'remove'
    """
    doc_type = 'enter' if change_type == 'add' else 'loss'
    prefix = 'O' if change_type == 'add' else 'S'
    name = f"{prefix}-{get_current_datetime('%Y-%m-%d-%H%M%S')}"
    doc = ms_client.create_registration(org_id, store_id, project_id, name) if change_type == 'add' \
        else ms_client.create_write_off(org_id, store_id, project_id, name)
    return ms_client.create_positions_for_doc(doc.get('id', ''), positions, doc_type=doc_type) if doc else {}
