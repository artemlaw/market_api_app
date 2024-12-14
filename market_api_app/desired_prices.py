import pandas as pd
from market_api_app import get_api_tokens, MoySklad, get_stock_for_bundle, get_prime_cost, YaMarket, \
    get_ya_campaign_and_business_ids, chunked_offers_list, get_dict_for_commission, get_ya_data_for_article, ExcelStyle, \
    get_ya_data_for_order, get_ms_products, get_ym_orders


# Применить в colab в виде
# from google.colab import files
# report = get_ym_desired_prices(plan_margin=28.0, fbs=True)
# files.download(report)
def get_ym_desired_prices(plan_margin: float = 28.0, fbs: bool = True):
    ms_token, _, ym_token = get_api_tokens()
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

    campaign_id, business_id = get_ya_campaign_and_business_ids(
        ym_client, fbs=fbs
    )

    offers = ym_client.get_offers(business_id)

    print("ЯндексМаркет: Получение актуальных тарифов")
    offers_commission_dict = chunked_offers_list(
        get_dict_for_commission,
        ym_client=ym_client,
        campaign_id=campaign_id,
        data=offers,
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
    # print(df)
    path_xls_file = f'ya_{"fbs" if fbs else "express"}_рекомендуемые_цены.xlsx'
    style = ExcelStyle()
    style.style_dataframe(df, path_xls_file, "Номенклатура YA")
    print("Файл отчета готов")
    return path_xls_file


def get_ym_profitability(from_date: str, to_date: str, plan_margin: float = 28.0, fbs: bool = True):
    ms_token, _, ym_token = get_api_tokens()
    ms_client = MoySklad(ms_token)
    ms_products = get_ms_products(ms_client, project='ЯндексМаркет')

    ym_client = YaMarket(api_key=ym_token)
    campaign_id, business_id = get_ya_campaign_and_business_ids(
        ym_client, fbs=fbs
    )

    offers = ym_client.get_offers(business_id)

    print("ЯндексМаркет: Получение актуальных тарифов")
    offers_commission_dict = chunked_offers_list(
        get_dict_for_commission,
        ym_client=ym_client,
        campaign_id=campaign_id,
        data=offers,
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
    style.style_dataframe(df, path_xls_file, "Номенклатура YA")
    print("Файл отчета готов")
    return path_xls_file


if __name__ == '__main__':
    # get_ym_desired_prices(plan_margin=28.0, fbs=True)
    get_ym_profitability('13-12-2024', '14-12-2024', plan_margin=28.0, fbs=True)
