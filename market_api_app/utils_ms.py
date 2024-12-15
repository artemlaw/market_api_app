import logging
import re

from market_api_app import MoySklad

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MS Utils')


def get_product_id_from_url(url: str) -> str | None:
    pattern = r'/product/([0-9a-fA-F-]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    else:
        return None


def get_stock_for_bundle(stocks_dict: dict, product: list) -> float:
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


def get_ms_products(client: MoySklad, project: str = 'ЯндексМаркет') -> dict:
    """
    Получение товаров по project - значения 'ЯндексМаркет', 'Озон'
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
    return {
        product["article"]: {
            "STOCK": get_stock_for_bundle(ms_stocks, product),
            "PRIME_COST": get_prime_cost(product.get("salePrices", [])),
            "NAME": product["name"],
        }
        for product in products_for_project
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
