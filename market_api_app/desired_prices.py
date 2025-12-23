import pandas as pd
from market_api_app import MoySklad, YaMarket, Ozon, WB, ExcelStyle, get_api_keys
from market_api_app.utils import add_regions_sum_immutable
from market_api_app.utils_gs import get_table, get_column_values_by_index
from market_api_app.utils_ms import get_stock_for_bundle, get_prime_cost, get_ms_products, get_ms_products_for_wb, \
    get_stocks_wh, get_cards_prices, get_stocks_wh_full
from market_api_app.utils_ozon import get_oz_orders, get_oz_data_for_order, print_oz_constants, get_oz_data_for_article
from market_api_app.utils_wb import get_logistic_dict, get_price_dict, get_category_dict, get_wb_data_for_article, \
    wb_get_orders, get_order_data, get_category_subject_id_dict
from market_api_app.utils_ya import get_category_ids, chunked_offers_list, get_dict_for_commission, \
    get_ya_data_for_article, get_ym_orders, get_ya_data_for_order

'''
Использовать в Colab в виде:
from google.colab import files
report = get_ym_desired_prices(plan_margin=28.0, fbs=True)
files.download(report)
'''


def get_ym_desired_prices(plan_margin: float = 28.0, fbs: bool = True):
    campaign_id_key = "YA_FBS_CAMPAIGN_ID" if fbs else "YA_EXPRESS_CAMPAIGN_ID"
    ms_token, ym_token, business_id, campaign_id = get_api_keys(["MS_API_TOKEN", "YM_API_TOKEN", "YA_BUSINESS_ID",
                                                                 campaign_id_key])
    ms_client = MoySklad(api_key=ms_token)
    products_ = ms_client.get_bundles()
    # print(f"Мой склад: {len(products_)}")
    # Оставляем только Яндекс
    ms_ya_products = [p for p in products_ if p.get('pathName', '') == 'ЯндексМаркет']

    print("Мой склад: Получение остатка товара")
    stocks = ms_client.get_stock()
    ms_stocks = {stock["assortmentId"]: stock["quantity"] for stock in stocks}
    print("Мой склад: Получение себестоимости товара")
    ms_ya_products_ = {
        product["article"]: {
            "STOCK": get_stock_for_bundle(ms_stocks, product),
            "PRIME_COST": get_prime_cost(product.get("salePrices", [])),
            "NAME": product["name"],
        }
        for product in ms_ya_products
    }

    ym_client = YaMarket(api_key=ym_token)
    offers = ym_client.get_offers(business_id)

    category_ids = get_category_ids(ym_client)

    print("ЯндексМаркет: Получение актуальных тарифов")
    offers_commission_dict = chunked_offers_list(
        get_dict_for_commission,
        ym_client=ym_client,
        campaign_id=campaign_id,
        data=offers,
        category_ids=category_ids,
        chunk_size=200,
    )

    ya_set = set(offers_commission_dict)
    ms_set = set(ms_ya_products_)

    result_dict = {
        key: {**offers_commission_dict.get(key, {}), **ms_ya_products_.get(key, {})}
        for key in ya_set & ms_set
    }

    ya_ms_set = ya_set - ms_set
    if ya_ms_set:
        print("Номенклатура которая есть в ЯндексМаркете, но не связана в МС:")
        print("\n".join(ya_ms_set))

    data_for_report = [
        get_ya_data_for_article(article, result_dict[article], plan_margin)
        for article in result_dict
    ]
    print('Формирую отчет "Рекомендуемые цены"')
    # progress_bar.update(50)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    df_total = (
        df.agg(
            {
                "stock": "sum",
                "price": "sum",
                "recommended_price": "sum",
                "prime_cost": "sum",
                "commission": "sum",
                "acquiring": "sum",
                "delivery": "sum",
                "crossregional_delivery": "sum",
                "sorting": "sum",
                "profit": "sum",
            }
        )
        .to_frame()
        .T
    )
    df_total["name"] = ""
    df_total["article"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)

    df = pd.concat([df, df_total], ignore_index=True)

    df.columns = [
        "Номенклатура",
        "Артикул",
        "Остаток",
        "Текущая цена",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Доставка",
        "Доставка в округ",
        "Обработка",
        "Прибыль",
        "Рентабельность",
    ]

    path_xls_file = f'ya_{"fbs" if fbs else "express"}_рекомендуемые_цены.xlsx'
    style = ExcelStyle()
    style.style_dataframe(df, path_xls_file, "Номенклатура YA")
    print("Файл отчета готов")
    return path_xls_file


def get_ym_profitability(from_date: str, to_date: str, plan_margin: float = 28.0, fbs: bool = True):
    campaign_id_key = "YA_FBS_CAMPAIGN_ID" if fbs else "YA_EXPRESS_CAMPAIGN_ID"
    ms_token, ym_token, business_id, campaign_id = get_api_keys(["MS_API_TOKEN", "YM_API_TOKEN", "YA_BUSINESS_ID",
                                                                 campaign_id_key])

    ms_client = MoySklad(ms_token)
    ms_products = get_ms_products(ms_client, project='ЯндексМаркет')

    ym_client = YaMarket(api_key=ym_token)
    offers = ym_client.get_offers(business_id)

    category_ids = get_category_ids(ym_client=ym_client)

    print("ЯндексМаркет: Получение актуальных тарифов")
    offers_commission_dict = chunked_offers_list(
        get_dict_for_commission,
        ym_client=ym_client,
        campaign_id=campaign_id,
        data=offers,
        category_ids=category_ids,
        chunk_size=200,
    )

    ya_set = set(offers_commission_dict)
    ms_set = set(ms_products)

    tariffs_dict = {
        key: {**offers_commission_dict.get(key, {}), **ms_products.get(key, {})}
        for key in ya_set & ms_set
    }

    ya_ms_set = ya_set - ms_set
    if ya_ms_set:
        print("Номенклатура которая есть в ЯндексМаркете, но не связана в МС:")
        print("\n".join(ya_ms_set))

    ym_orders = get_ym_orders(ym_client, campaign_id, from_date, to_date)
    print(f'ЯндексМаркет: Получено заказов - {len(ym_orders)}')

    data_for_report = [
        get_ya_data_for_order(order, tariffs_dict, plan_margin)
        for order in ym_orders
    ]

    print('Формирую отчет "Рентабельность заказов ЯндексМаркет"')
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    df_total = (
        df.agg(
            {
                "quantity": "sum",
                "stock": "sum",
                "price": "sum",
                "recommended_price": "sum",
                "prime_cost": "sum",
                "commission": "sum",
                "acquiring": "sum",
                "delivery": "sum",
                "crossregional_delivery": "sum",
                "sorting": "sum",
                "profit": "sum",
            }
        )
        .to_frame()
        .T
    )
    df_total["order_number"] = ""
    df_total["created"] = ""
    df_total["name"] = ""
    df_total["article"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)

    df = pd.concat([df, df_total], ignore_index=True)

    df.columns = [
        "Номер заказа",
        "Дата заказа",
        "Продано",
        "Номенклатура",
        "Артикул",
        "Остаток",
        "Текущая цена",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Доставка",
        "Доставка в округ",
        "Обработка",
        "Прибыль",
        "Рентабельность",
    ]
    # print(df)
    path_xls_file = f'ya_{"fbs" if fbs else "express"}_рентабельность_заказы.xlsx'
    style = ExcelStyle()
    style.style_dataframe(df, path_xls_file, "Заказы YA")
    print("Файл отчета готов")
    return path_xls_file


def get_oz_desired_prices(plan_margin: float = 28.0):
    ms_token, oz_client_id, oz_token = get_api_keys(["MS_API_TOKEN", "OZ_CLIENT_ID", "OZ_API_TOKEN"])

    ms_client = MoySklad(ms_token)
    ms_products = get_ms_products(ms_client, project='Озон')

    oz_client = Ozon(client_id=oz_client_id, api_key=oz_token)
    products = oz_client.get_products()

    print("Ozon: Получение актуальных тарифов")
    print_oz_constants()
    offers_commission_dict = {
        prod['offer_id']: {
            'acquiring': prod.get('acquiring', 0),
            'fbs_deliv_to_customer_amount': prod.get('commissions', {}).get('fbs_deliv_to_customer_amount', 0.0),
            'fbs_direct_flow_trans_max_amount': prod.get('commissions', {}).get('fbs_direct_flow_trans_max_amount', 0),
            'fbs_direct_flow_trans_min_amount': prod.get('commissions', {}).get('fbs_direct_flow_trans_min_amount', 0),
            'fbs_first_mile_max_amount': prod.get('commissions', {}).get('fbs_first_mile_max_amount', 0),
            'fbs_first_mile_min_amount': prod.get('commissions', {}).get('fbs_first_mile_min_amount', 0),
            'fbs_return_flow_amount': prod.get('commissions', {}).get('fbs_return_flow_amount', 0),
            'fbs_return_flow_trans_max_amount': prod.get('commissions', {}).get('fbs_return_flow_trans_max_amount', 0),
            'fbs_return_flow_trans_min_amount': prod.get('commissions', {}).get('fbs_return_flow_trans_min_amount', 0),
            'sales_percent_fbs': prod.get('commissions', {}).get('sales_percent_fbs', 0),
            'price': float(prod.get('price', {}).get('price', '0.0000')),
            'marketing_price': float(prod.get('price', {}).get('marketing_price', '0.0000')),
            'marketing_seller_price': float(prod.get('price', {}).get('marketing_seller_price', '0.0000')),
            'volume_weight': prod.get('volume_weight', 0.0)
        }
        for prod in products
    }

    oz_set = set(offers_commission_dict)
    ms_set = set(ms_products)

    tariffs_dict = {
        key: {**offers_commission_dict.get(key, {}), **ms_products.get(key, {})}
        for key in oz_set & ms_set
    }

    oz_ms_set = oz_set - ms_set
    if oz_ms_set:
        print("Номенклатура которая есть в Ozon, но не связана в МС:")
        print("\n".join(oz_ms_set))

    oz_ms_common_set = oz_set & ms_set

    if not oz_ms_common_set:
        return None

    data_for_report = [
        get_oz_data_for_article(article, tariffs_dict, plan_margin)
        for article in oz_ms_common_set
    ]

    print('Формирую отчет "Рекомендуемые цены Ozon"')
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    df_total = (
        df.agg(
            {
                "stock": "sum",
                "price": "sum",
                "recommended_price": "sum",
                "prime_cost": "sum",
                "commission": "sum",
                "acquiring": "sum",
                "delivery": "sum",
                "crossregional_delivery": "sum",
                "sorting": "sum",
                "profit": "sum",
            }
        )
        .to_frame()
        .T
    )
    df_total["name"] = ""
    df_total["article"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)

    df = pd.concat([df, df_total], ignore_index=True)

    df.columns = [
        "Номенклатура",
        "Артикул",
        "Остаток",
        "Цена продажи",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Логистика",
        "Доставка до места выдачи",
        "Обработка",
        "Прибыль",
        "Рентабельность",
    ]
    path_xls_file = f'ozon_fbs_рекомендуемые_цены.xlsx'
    style = ExcelStyle()
    style.style_dataframe(df, path_xls_file, "Номенклатура Ozon")
    print("Файл отчета готов")
    return path_xls_file


def get_oz_profitability(from_date: str, to_date: str, plan_margin: float = 28.0):
    ms_token, oz_client_id, oz_token = get_api_keys(["MS_API_TOKEN", "OZ_CLIENT_ID", "OZ_API_TOKEN"])

    ms_client = MoySklad(ms_token)
    ms_products = get_ms_products(ms_client, project='Озон')

    oz_client = Ozon(client_id=oz_client_id, api_key=oz_token)
    products = oz_client.get_products()

    print("Ozon: Получение актуальных тарифов")
    print_oz_constants()
    offers_commission_dict = {
        prod['offer_id']: {
            'acquiring': prod.get('acquiring', 0),
            'fbs_deliv_to_customer_amount': prod.get('commissions', {}).get('fbs_deliv_to_customer_amount', 0.0),
            'fbs_direct_flow_trans_max_amount': prod.get('commissions', {}).get('fbs_direct_flow_trans_max_amount', 0),
            'fbs_direct_flow_trans_min_amount': prod.get('commissions', {}).get('fbs_direct_flow_trans_min_amount', 0),
            'fbs_first_mile_max_amount': prod.get('commissions', {}).get('fbs_first_mile_max_amount', 0),
            'fbs_first_mile_min_amount': prod.get('commissions', {}).get('fbs_first_mile_min_amount', 0),
            'fbs_return_flow_amount': prod.get('commissions', {}).get('fbs_return_flow_amount', 0),
            'fbs_return_flow_trans_max_amount': prod.get('commissions', {}).get('fbs_return_flow_trans_max_amount', 0),
            'fbs_return_flow_trans_min_amount': prod.get('commissions', {}).get('fbs_return_flow_trans_min_amount', 0),
            'sales_percent_fbs': prod.get('commissions', {}).get('sales_percent_fbs', 0),
            'price': float(prod.get('price', {}).get('price', '0.0000')),
            'marketing_price': float(prod.get('price', {}).get('marketing_price', '0.0000')),
            'marketing_seller_price': float(prod.get('price', {}).get('marketing_seller_price', '0.0000')),
            'volume_weight': prod.get('volume_weight', 0.0)
        }
        for prod in products
    }

    oz_set = set(offers_commission_dict)
    ms_set = set(ms_products)

    tariffs_dict = {
        key: {**offers_commission_dict.get(key, {}), **ms_products.get(key, {})}
        for key in oz_set & ms_set
    }

    oz_ms_set = oz_set - ms_set
    if oz_ms_set:
        print("Номенклатура которая есть в Ozon, но не связана в МС:")
        print("\n".join(oz_ms_set))

    oz_orders = get_oz_orders(oz_client, from_date, to_date)

    data_for_report = [
        get_oz_data_for_order(order, tariffs_dict, plan_margin)
        for order in oz_orders
    ]

    print('Формирую отчет "Рентабельность заказов Ozon"')
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    df_total = (
        df.agg(
            {
                "quantity": "sum",
                "stock": "sum",
                "price": "sum",
                "recommended_price": "sum",
                "prime_cost": "sum",
                "commission": "sum",
                "acquiring": "sum",
                "delivery": "sum",
                "crossregional_delivery": "sum",
                "sorting": "sum",
                "profit": "sum",
            }
        )
        .to_frame()
        .T
    )
    df_total["order_number"] = ""
    df_total["created"] = ""
    df_total["name"] = ""
    df_total["article"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)

    df = pd.concat([df, df_total], ignore_index=True)

    df.columns = [
        "Номер заказа",
        "Дата заказа",
        "Продано",
        "Номенклатура",
        "Артикул",
        "Остаток",
        "Цена продажи",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Логистика",
        "Доставка до места выдачи",
        "Обработка",
        "Прибыль",
        "Рентабельность",
    ]
    path_xls_file = f'ozon_fbs_рентабельность_заказы.xlsx'
    style = ExcelStyle()
    style.style_dataframe(df, path_xls_file, "Заказы Ozon")
    print("Файл отчета готов")
    return path_xls_file


def get_null_nm_id(order_nm_id):
    print(f'Номенклатура которая есть на WB, но не связана в МС: {order_nm_id}')
    return {
        "STOCK": 0.0,
        "STOCK_FBS": 0,
        "STOCK_FBO": 0,
        "PRIME_COST": 0.0,
        "NAME": "Нет данных в МС",
        "ARTICLE": "Нет данных в МС",
        "CATEGORY": "",
        "VOLUME": 1
    }


def get_wb_profitability(from_date: str, to_date: str, plan_margin: float = 28.0, acquiring: float = 1.6,
                         one_fbs: bool = False, save_to_gs: bool = False, save_to_tab: bool = False,
                         file_settings: str = None, table_key: str = None, sheet_out: str = None):
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    wb_client = WB(api_key=wb_token)
    orders_fbs, orders_fbo, nm_ids_fbs, nm_ids_fbo = wb_get_orders(wb_client, from_date, to_date)
    nm_ids_list = list(nm_ids_fbo) if one_fbs else list(nm_ids_fbs | nm_ids_fbo)

    ms_client = MoySklad(ms_token)
    ms_products_with_stocks = get_ms_products_for_wb(ms_client, one_fbs, nm_ids_list)

    tariffs_data = wb_client.get_tariffs_for_box()
    category_dict = get_category_dict(wb_client)
    wb_prices_dict = get_price_dict(wb_client)

    base_dict = {
        'tariffs_data': tariffs_data,
        'category_dict': category_dict,
        'wb_prices_dict': wb_prices_dict
    }

    if one_fbs:
        orders_fbs = []

    data_for_report = []
    not_in_ms = []
    for orders, is_fbs in [(orders_fbo, False), (orders_fbs, True)]:
        for order in orders:
            # Для переопределения значения по умолчанию можно использовать get_null_nm_id(order.get('nmId'))
            product_dict = ms_products_with_stocks.get(order.get('nmId'), {})
            if product_dict and order.get('nmId') in nm_ids_list:
                data_for_report.append(
                    get_order_data(
                        order,
                        product_dict,
                        base_dict,
                        plan_margin=plan_margin,
                        acquiring=acquiring,
                        fbs=is_fbs
                    )
                )
            else:
                not_in_ms.append(order.get('nmId'))

    if not_in_ms:
        print('Количество заказов не вошедших в отчет: ', len(not_in_ms))
        print('Список товаров по которым нет данных в МС, либо код товара в МС не соответствует WB:')
        not_in_ms_set = set(not_in_ms)
        print(", ".join(map(str, not_in_ms_set)))

    print('Формирую отчет "Рентабельность заказов WB"')
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    df_total = (
        df.agg(
            {
                "stock": "sum",
                "stock_fbs": "sum",
                "stock_fbo": "sum",
                "quantity": "sum",
                "price": "sum",
                "order_price": "sum",
                "recommended_price": "sum",
                "prime_cost": "sum",
                "commission": "sum",
                "acquiring": "sum",
                "logistics": "sum",
                "profit": "sum",
                "order_profit": "sum",

            }
        )
        .to_frame()
        .T
    )
    df_total["name"] = ""
    df_total["url"] = ""
    df_total["nm_id"] = ""
    df_total["article"] = ""
    df_total["order_create"] = ""
    df_total["order_name"] = ""
    df_total["discount"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)
    df_total["order_profitability"] = round((df_total["order_profit"] / df_total["order_price"]) * 100, 1)

    df_ = pd.concat([df, df_total], ignore_index=True)
    df_.columns = [
        "Номенклатура",
        "Артикул",
        "NmId",
        "Ссылка",
        "Остаток",
        "FBS остаток в корзине",
        "FBO остаток в корзине",
        "Дата заказа",
        "Номер заказа",
        "Количество",
        "Дисконт, %",
        "Текущая цена",
        "Цена заказа",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Логистика",
        "Прибыль",
        "Рентабельность",
        "Прибыль по заказу",
        "Рентабельность по заказу",
    ]
    # print(df)
    path_xls_file = 'wb_рентабельность_по_заказам.xlsx'
    columns_to_align_right = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
    style = ExcelStyle(columns_to_align_right=columns_to_align_right)

    df_group = ((
        df.groupby(['name', 'nm_id', 'article'])[
            ["discount", "stock", "stock_fbs", "stock_fbo", "quantity"]
        ].agg({
            "discount": "max",
            "stock": "max",
            "stock_fbs": "max",
            "stock_fbo": "max",
            "quantity": "sum"
        }).reset_index()
    ).rename(columns={
        'name': 'Номенклатура',
        'article': 'Артикул',
        'nm_id': 'NmId',
        'discount': 'Дисконт, %',
        'stock': 'Остаток',
        'stock_fbs': 'FBS остаток в корзине',
        'stock_fbo': 'FBO остаток в корзине',
        'quantity': 'Продажи'})
    )

    if save_to_gs:
        # Преобразование DataFrame в список списков и обновление листа
        wb_table = get_table(file_settings, table_key)
        data = [df_group.columns.values.tolist()] + df_group.values.tolist()
        sheet = wb_table.worksheet(sheet_out)
        sheet.clear()
        sheet.update(range_name="A1", values=data)
        print(f'Данные успешно сохранены на лист "{sheet_out}" в таблице "{wb_table}".')

    if save_to_tab:
        style.style_dataframe(df_, path_xls_file, sheet_title="Заказы WB")
        style.style_dataframe(df_group, path_xls_file, sheet_title="Сводный", active_sheet=False)
        print("Файл отчета готов")
    return path_xls_file


def get_wb_desired_prices(plan_margin: float = 28.0, acquiring: float = 1.6, fbs: bool = True):
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])

    wb_client = WB(api_key=wb_token)

    tariffs_data = wb_client.get_tariffs_for_box()
    warehouse_name = 'Маркетплейс: Центральный федеральный округ' if fbs else 'Подольск'
    logistic_dict = get_logistic_dict(tariffs_data, warehouse_name, fbs)
    category_dict = get_category_dict(wb_client)
    wb_prices_dict = get_price_dict(wb_client)

    ms_client = MoySklad(api_key=ms_token)
    # Получаем номенклатуру из МС только WB
    fbo = not fbs
    ms_wb_products = get_ms_products_for_wb(ms_client, fbo)
    data_for_report = [
        get_wb_data_for_article(nm_id, ms_wb_products[nm_id], wb_prices_dict[nm_id], category_dict, logistic_dict,
                                plan_margin, acquiring, fbs, fbo)
        for nm_id in ms_wb_products if nm_id in wb_prices_dict
    ]
    print('Формирую отчет "Рекомендуемые цены"')
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    df = pd.DataFrame(data_for_report)
    data_total = {
        "stock": "sum",
        "price": "sum",
        "recommended_price": "sum",
        "prime_cost": "sum",
        "commission": "sum",
        "acquiring": "sum",
        "logistics": "sum",
        "profit": "sum",
    }
    if fbo:
        data_total["stock_fbs"] = "sum"
        data_total["stock_fbo"] = "sum"

    df_total = (
        df.agg(
            data_total
        )
        .to_frame()
        .T
    )
    df_total["name"] = ""
    df_total["url"] = ""
    df_total["nm_id"] = ""
    df_total["article"] = ""
    df_total["discount"] = ""
    df_total["profitability"] = round((df_total["profit"] / df_total["price"]) * 100, 1)

    df = pd.concat([df, df_total], ignore_index=True)
    columns = [
        "Номенклатура",
        "Артикул",
        "NmId",
        "Ссылка",
        "Остаток",
        "Дисконт, %",
        "Текущая цена",
        "Рекомендуемая цена",
        "Себестоимость",
        "Комиссия",
        "Эквайринг",
        "Логистика",
        "Прибыль",
        "Рентабельность",
    ]
    if fbo:
        columns = [
            "Номенклатура",
            "Артикул",
            "NmId",
            "Ссылка",
            "Остаток",
            "FBS остаток в корзине",
            "FBO остаток в корзине",
            "Дисконт, %",
            "Текущая цена",
            "Рекомендуемая цена",
            "Себестоимость",
            "Комиссия",
            "Эквайринг",
            "Логистика",
            "Прибыль",
            "Рентабельность",
        ]

    df.columns = columns
    # print(df)
    path_xls_file = f'wb_{"fbs" if fbs else "fbo"}_рекомендуемые_цены.xlsx'
    columns_to_align_right = [9, 10, 11, 12, 13] if fbo else [7, 8, 9, 10, 11, 12]
    style = ExcelStyle(columns_to_align_right=columns_to_align_right)
    style.style_dataframe(df, path_xls_file, "Номенклатура WB")
    print("Файл отчета готов")
    return path_xls_file


def update_stocks_in_tabs(file_settings: str, table_key: str, sheet_in: str, sheet_out: str):
    wb_table = get_table(file_settings, table_key)
    nm_ids = get_column_values_by_index(wb_table, sheet_in, 4)

    client = MoySklad(api_key='')
    stocks_data_ = get_stocks_wh(client, nm_ids)

    stocks_data = add_regions_sum_immutable(stocks_data_, ['Котовск WB', 'Волгоградская обл.WB',
                                                           'Екатеринбург WB', 'Воронеж WB', 'Краснодар WB',
                                                           'Новосибирск WB', 'Невинномысск WB'])

    # Сбор всех уникальных ключей из массивов словарей
    unique_keys = set(key for _, _, dicts in stocks_data.values() for d in dicts for key in d)
    # Вычисление суммы значений для каждого уникального ключа
    key_sums = {}
    for _, _, dicts in stocks_data.values():
        for d in dicts:
            for k, v in d.items():
                key_sums[k] = key_sums.get(k, 0) + v

    sorted_keys = ["FBS", "Екатеринбург WB", "Регионы"] + sorted((key for key in unique_keys if key != "FBS"
                                                                  and key != "Екатеринбург WB" and key != "Регионы"),
                                                                 key=lambda x: -key_sums[x])
    # Преобразование данных
    rows = []
    for key, values in stocks_data.items():
        # Извлекаем элементы кортежа
        first_value = values[0]
        second_value = values[1]
        dict_list = values[2]

        # Создаем строку для DataFrame
        row = [key, first_value, second_value]
        # Добавляем значения для каждого уникального ключа
        for uk in sorted_keys:
            # Ищем значение для текущего уникального ключа
            value = 0  # Значение по умолчанию
            for d in dict_list:
                if uk in d:
                    value = d[uk]
                    break
            row.append(value)
        rows.append(row)

    # Создаем DataFrame
    columns = ['NmID', 'FBS остаток', 'FBO остаток'] + sorted_keys
    df = pd.DataFrame(rows, columns=columns)

    # Преобразование DataFrame в список списков и обновление листа
    data = [df.columns.values.tolist()] + df.values.tolist()
    sheet = wb_table.worksheet(sheet_out)
    sheet.clear()
    sheet.update(range_name="A1", values=data)
    print(f"Данные успешно сохранены на лист в таблице '{wb_table}'.")


def update_prices_in_tabs(file_settings: str, table_key: str, sheet_out: str):
    wb_table = get_table(file_settings, table_key)

    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    ms_client = MoySklad(api_key=ms_token)
    wb_client = WB(api_key=wb_token)
    wb_prices = get_price_dict(wb_client)
    category_dict = get_category_subject_id_dict(wb_client)

    nm_ids = list(wb_prices.keys())

    cards_prices = {key: {'discount': wb_prices.get(key, {}).get('discount', 0),
                          'price': wb_prices.get(key, {}).get('price', 0), **value} for key, value
                    in get_cards_prices(ms_client, nm_ids).items()}
    # Преобразование данных
    rows = []
    for key, values in cards_prices.items():
        # Извлекаем элементы
        price = values.get('price', 0)
        discount = values.get('discount', 0)
        shop_price = values.get('shop_price', 0)
        basket_price = values.get('basket_price', 0)
        fbs_stock = values.get('fbs_stock', 0)
        fbo_stock = values.get('fbo_stock', 0)
        category_id = values.get('category', '')
        fbs_commission = category_dict.get(category_id, (0, 0))[0]
        fbo_commission = category_dict.get(category_id, (0, 0))[1]
        if price == 0:
            spp = 0
        else:
            spp = round((1 - round(basket_price / price, 2)) * 100, 1)
        # spp = 100 - math.floor(basket_price / price * 100)
        if spp >= 100:
            spp = 0
        # Создаем строку для DataFrame
        row = [key, shop_price, discount, price, basket_price, spp, fbs_stock, fbo_stock, fbs_commission,
               fbo_commission]
        rows.append(row)

    # Создаем DataFrame
    columns = ['NmID', 'Цена до скидки', 'Скидка магазина', 'Цена без скидки', 'Цена в корзине', 'СПП', 'FBS остаток',
               'FBO остаток', 'FBS комиссия', 'FBO комиссия']

    df = pd.DataFrame(rows, columns=columns)
    # Преобразование DataFrame в список списков и обновление листа
    data = [df.columns.values.tolist()] + df.values.tolist()
    sheet = wb_table.worksheet(sheet_out)
    sheet.clear()
    sheet.update(range_name="A1", values=data)
    print(f"Данные успешно сохранены на лист в таблице '{wb_table}'.")


def get_wb_orders(from_date: str, to_date: str):
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    wb_client = WB(api_key=wb_token)
    # orders_fbs, orders_fbo, nm_ids_fbs, nm_ids_fbo = wb_get_orders(wb_client, from_date, to_date)
    orders = wb_client.get_orders(from_date)
    alen = []
    for order in orders:
        order_data = order.get("date")
        # if order_data and order_data >= "2025-07-04T21:00:00":
        if order_data and order_data <= "2025-07-05T21:00:00":
        #     print(order)
            alen.append(order)
    print(len(alen))
    # 90
    # 655 от 04

    return len(orders)


def update_stocks_in_tabs_v2(file_settings: str, table_key: str, sheet_in: str, sheet_out: str):
    wb_table = get_table(file_settings, table_key)
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    ms_client = MoySklad(api_key=ms_token)
    # wb_client = WB(api_key=wb_token)
    # wb_prices = get_price_dict(wb_client)

    nm_ids = get_column_values_by_index(wb_table, sheet_in, 4)
    # nm_ids = list(wb_prices.keys())

    stocks_data_ = get_stocks_wh_full(ms_client, nm_ids)
    stocks_data = add_regions_sum_immutable(stocks_data_, ['Котовск WB', 'Волгоградская обл.WB',
                                                           'Екатеринбург WB', 'Воронеж WB', 'Краснодар WB',
                                                           'Новосибирск WB', 'Невинномысск WB'])

    # Сбор всех уникальных ключей из массивов словарей
    unique_keys = set(key for _, _, dicts in stocks_data.values() for d in dicts for key in d)
    # Вычисление суммы значений для каждого уникального ключа
    key_sums = {}
    for _, _, dicts in stocks_data.values():
        for d in dicts:
            for k, v in d.items():
                key_sums[k] = key_sums.get(k, 0) + v

    sorted_keys = ["FBS", "Екатеринбург WB", "Регионы"] + sorted((key for key in unique_keys if key != "FBS"
                                                                  and key != "Екатеринбург WB" and key != "Регионы"),
                                                                 key=lambda x: -key_sums[x])
    # Преобразование данных
    rows = []
    for key, values in stocks_data.items():
        # Извлекаем элементы кортежа
        first_value = values[0]
        second_value = values[1]
        dict_list = values[2]

        # Создаем строку для DataFrame
        row = [key, first_value, second_value]
        # Добавляем значения для каждого уникального ключа
        for uk in sorted_keys:
            # Ищем значение для текущего уникального ключа
            value = 0  # Значение по умолчанию
            for d in dict_list:
                if uk in d:
                    value = d[uk]
                    break
            row.append(value)
        rows.append(row)

    # Создаем DataFrame
    columns = ['NmID', 'FBS остаток', 'FBO остаток'] + sorted_keys
    df = pd.DataFrame(rows, columns=columns)

    # Преобразование DataFrame в список списков и обновление листа
    data = [df.columns.values.tolist()] + df.values.tolist()
    sheet = wb_table.worksheet(sheet_out)
    sheet.clear()
    sheet.update(range_name="A1", values=data)
    print(f"Данные успешно сохранены на лист в таблице '{wb_table}'.")


def update_stocks_in_tabs_v3(file_settings: str, table_key: str, sheet_in: str, sheet_out: str):
    # wb_table = get_table(file_settings, table_key)
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    ms_client = MoySklad(api_key=ms_token)
    wb_client = WB(api_key=wb_token)
    wb_prices = get_price_dict(wb_client)
    nm_ids = list(wb_prices.keys())

    for nd_id in nm_ids:
        offices_stocks = wb_client.get_stocks_for_nm_id(nm_id=nd_id, from_date='2025-12-01', to_date='2025-12-01')
        stock_dict = {}
        for office in offices_stocks:
            office_name = 'FBS' if office.get('regionName', '') == 'Маркетплейс' else office.get('officeName', '')
            # office_id = office.get('officeID', 0)
            # stock_count = office.get('stockCount', 0)
            #
            # office.get('regionName', 'FBO') : office.get('stockCount', 0)

            stock_dict[office_name] = office.get('metrics', {}).get('stockCount', 0)

        wb_prices[nd_id]['stocks'] = stock_dict
        print(wb_prices[nd_id])

    print(wb_prices)


if __name__ == '__main__':
    # get_ym_desired_prices(plan_margin=28.0, fbs=True)
    # ya = get_ym_profitability('10-12-2025', '10-12-2025', plan_margin=28.0, fbs=True)
    # print(ya)
    # oz = get_oz_profitability('04-06-2025', '05-06-2025', plan_margin=28.0)
    # oz = get_oz_desired_prices(plan_margin=28.0)
    # print(oz)

    wb_orders = get_wb_profitability('2025-12-23', '2025-12-23', plan_margin=28.0, acquiring=1.6,
                                     one_fbs=True, save_to_tab=True)
    # wb_orders = get_wb_orders('2025-08-07', '2025-08-07')
    print(wb_orders)

    # client = MoySklad(api_key='')
    # stocks_data = get_stocks_wh(client, [251840861,])
    # print(stocks_data)

    # wb = get_wb_desired_prices(plan_margin=28.0, fbs=False)
    # print(wb)

    # campaign_id_key = "YA_FBS_CAMPAIGN_ID"
    # ms_token, ym_token, business_id, campaign_id = get_api_keys(["MS_API_TOKEN", "YM_API_TOKEN", "YA_BUSINESS_ID",
    #                                                              campaign_id_key])
    #
    # ym_client = YaMarket(api_key=ym_token)
    # tree = ym_client.get_tree()
    # print(tree)

    # update_stocks_in_tabs(file_settings, table_id, sheet_in, sheet_out)

    # update_stocks_in_tabs_v2("", "", "", "")

    # update_prices_in_tabs("", "", "")

    # ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    # # ms_client = MoySklad(api_key=ms_token)
    # wb_client = WB(api_key=wb_token)
    # wb_stocks = wb_client.get_stocks_report_for_products("2025-11-20", "2025-11-20")
    # # wb_stocks = wb_client.get_stocks()
    # # a = {p.get('nmId'): p.get('quantityFull') for p in wb_stocks}
    # print(wb_stocks)

    # update_stocks_in_tabs_v3("", "", "", "")
