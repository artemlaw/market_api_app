import logging
from market_api_app import YaMarket
from market_api_app.utils import get_api_keys, get_value_by_name

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('YM Utils')

# Константа можно вынести в перспективе в файл настроек модуля
transit_warehouse_type = 'central_sorting_center'  # Склад сортировки. Определяет стоимость обработки


def get_all_ids(categories):
    ids = [category['id'] for category in categories]
    for category in categories:
        if 'children' in category:
            ids.extend(get_all_ids(category['children']))
    return ids


def get_category_ids(ym_client: YaMarket) -> list:
    tree = ym_client.get_tree()
    ids = get_all_ids(tree)
    return ids


def get_ya_campaign_and_business_ids(ym_client: YaMarket, fbs: bool = True):
    ids = get_api_keys(["YA_FBS_CAMPAIGN_ID", "YA_EXPRESS_CAMPAIGN_ID", "YA_BUSINESS_ID"])
    campaign_id, business_id = (ids[0], ids[2]) if fbs else (ids[1], ids[2])

    if campaign_id and business_id:
        return campaign_id, business_id
    else:
        campaigns = ym_client.get_campaigns()
        campaign = campaigns.get("campaigns", [])[0]
        campaign_id = int(campaign.get("id"))
        business_id = int(campaign.get("business", {}).get("id"))
        return campaign_id, business_id


def chunked_offers_list(func, ym_client, campaign_id, data: list, category_ids: list, chunk_size: int = 200):
    result = {}
    for i in range(0, len(data), chunk_size):
        chunk_data = data[i: i + chunk_size]
        result = {**result, **func(ym_client, campaign_id, chunk_data, category_ids)}
    return result


def get_dict_for_commission(ym_client: YaMarket, campaign_id: int, offers: list, category_ids: list) -> dict:
    if len(offers) > 200:
        logger.error("Ограничение запроса комиссии! Не более 200 товаров")
        offers = offers[:200]

    # Проверка актуальности категории
    for offer in offers:
        offer_mapping = offer.get("mapping", {})
        if offer_mapping.get("marketCategoryId", 0) not in category_ids:
            print(offer.get("offer", {}).get("offerId"), '- неактуальная категория:',
                  offer_mapping.get('marketCategoryName', ''))
            # 18% 'Шланги и комплекты для полива'
            offer["mapping"] = {
                'marketCategoryId': 13793401,
                'marketCategoryName': 'Шаблонная категория, 18%',
                'marketModelId': 100000000,
                'marketModelName': 'Шаблонная категория, 18%',
                'marketSku': 100000000000,
                'marketSkuName': ''
            }

    dimensions = 0
    offers_data = [
        {
            "categoryId": offer.get("mapping", {}).get("marketCategoryId", 0),
            "price": offer_data.get("basicPrice", {}).get("value", 0.0),
            "length": dimensions.get("length", 0),
            "width": dimensions.get("width", 0),
            "height": dimensions.get("height", 0),
            "weight": dimensions.get("weight", 0),
            "quantity": 1,
        }
        for offer in offers
        if (offer_data := offer.get("offer", {}))
           and (dimensions := offer_data.get("weightDimensions", {}))
    ]

    offers_dict = {
        index: (
            offer_.get("offer", {}).get("offerId", ""),
            offer_.get("offer", {}).get("basicPrice", {}).get("value", 0.0),
        )
        for index, offer_ in enumerate(offers)
    }

    commission = ym_client.get_categories(campaign_id=campaign_id, offers=offers_data)

    commission_dict = {}
    for i, comm in enumerate(commission):
        tariffs = comm.get("tariffs", [])
        tariff_values = {
            "PRICE": 0.0,
            "FEE": {"current_amount": 0.0, "percent": 0.0},
            "AGENCY_COMMISSION": 0.0,
            "PAYMENT_TRANSFER": {"current_amount": 0.0, "percent": 0.0},
            "DELIVERY_TO_CUSTOMER": {
                "current_amount": 0.0,
                "percent": 0.0,
                "max_value": 0.0,
            },
            "CROSSREGIONAL_DELIVERY": 0.0,
            "EXPRESS_DELIVERY": {
                "current_amount": 0.0,
                "percent": 0.0,
                "min_value": 0.0,
                "max_value": 0.0,
            },
            "SORTING": 0.0,
            "MIDDLE_MILE": 0.0,
        }

        for tariff in tariffs:
            tariff_type = tariff.get("type")
            amount = tariff.get("amount", 0.0)
            parameters = tariff.get("parameters", [])

            if tariff_type == "FEE" and parameters:
                tariff_values["FEE"]["current_amount"] = amount
                tariff_values["FEE"]["percent"] = float(
                    get_value_by_name(parameters, "value")
                )

            elif tariff_type == "PAYMENT_TRANSFER" and parameters:
                tariff_values["PAYMENT_TRANSFER"]["current_amount"] = amount
                tariff_values["PAYMENT_TRANSFER"]["percent"] = float(
                    get_value_by_name(parameters, "value")
                )

            elif tariff_type == "DELIVERY_TO_CUSTOMER" and parameters:
                tariff_values["DELIVERY_TO_CUSTOMER"]["current_amount"] = amount
                tariff_values["DELIVERY_TO_CUSTOMER"]["percent"] = float(
                    get_value_by_name(parameters, "value")
                )
                tariff_values["DELIVERY_TO_CUSTOMER"]["max_value"] = float(
                    get_value_by_name(parameters, "maxValue")
                )

            elif tariff_type == "EXPRESS_DELIVERY" and parameters:
                tariff_values["EXPRESS_DELIVERY"]["current_amount"] = amount
                tariff_values["EXPRESS_DELIVERY"]["percent"] = float(
                    get_value_by_name(parameters, "value")
                )
                tariff_values["EXPRESS_DELIVERY"]["min_value"] = float(
                    get_value_by_name(parameters, "minValue")
                )
                tariff_values["EXPRESS_DELIVERY"]["max_value"] = float(
                    get_value_by_name(parameters, "maxValue")
                )

            elif tariff_type == "SORTING" and parameters:
                if (
                        get_value_by_name(parameters, "transitWarehouseType")
                        == transit_warehouse_type
                ):
                    tariff_values["SORTING"] = amount

            elif tariff_type in tariff_values:
                tariff_values[tariff_type] = amount

        tariff_values["PRICE"] = offers_dict[i][1]
        article = offers_dict[i][0]

        commission_dict[article] = tariff_values

    return commission_dict


def get_ym_orders(ym_client: YaMarket, campaign_id: int = 0, from_date='12-12-2024', to_date='13-12-2024'):
    print('ЯндексМаркет: Получение заказов')
    ym_orders = ym_client.get_orders(campaign_id, from_date, to_date)
    return [
        {
            'order_number': order.get('id', 99999999999),
            'created': order.get('creationDate', ''),
            'article': position.get('offerId', ''),
            'price': position.get('price', 0.0) + position.get('subsidy', 0.0),
            'quantity': position.get('count', 0)
        }
        for order in ym_orders
        if order.get('status', '') not in ['CANCELLED']
        for position in order.get('items', [])
    ]


def get_ya_data_for_article(article, article_data, plan_margin: float = 28.0):
    margin = round(plan_margin / 100, 3)
    price = article_data.get("PRICE", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)
    commission_cost = round(article_data.get("FEE").get("current_amount", 0.0), 1)
    agency_commission = article_data.get("AGENCY_COMMISSION", 0.0)
    acquiring_cost = round(
        article_data.get("PAYMENT_TRANSFER").get("current_amount", 0.0)
        + agency_commission,
        1,
    )
    delivery_cost = round(
        article_data.get("DELIVERY_TO_CUSTOMER").get("current_amount", 0.0)
        + article_data.get("EXPRESS_DELIVERY").get("current_amount", 0.0),
        1,
    )
    delivery_cross_cost = article_data.get("CROSSREGIONAL_DELIVERY", 0.0)
    sorting = article_data.get("SORTING", 0.0)

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

    commission_percent = round(article_data.get("FEE", {}).get("percent", 0.0) / 100, 3)
    payment_percent = round(
        article_data.get("PAYMENT_TRANSFER", {}).get("percent", 0.0) / 100, 3
    )

    delivery_cost_percent = round(
        article_data.get("DELIVERY_TO_CUSTOMER", {}).get("percent", 0.0) / 100, 3
    )

    express_delivery_percent = round(
        article_data.get("EXPRESS_DELIVERY", {}).get("percent", 0.0) / 100, 3
    )

    delivery_percent = round(delivery_cost_percent + express_delivery_percent, 3)

    # TODO: Вынести расчет рекомендуемой цены в отдельную функцию
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

    if delivery_cost_max:
        delivery_cost_ = min(
            recommended_price * delivery_cost_percent, delivery_cost_max
        )
        recommended_price = round(
            (prime_cost + agency_commission + delivery_cross_cost + sorting + delivery_cost_)
            / (1 - margin - commission_percent - payment_percent)
        )
    elif express_delivery_max:
        express_delivery_ = max(
            min(recommended_price * express_delivery_percent, express_delivery_max),
            express_delivery_min,
        )
        recommended_price = round(
            (prime_cost + agency_commission + delivery_cross_cost + sorting + express_delivery_)
            / (1 - margin - commission_percent - payment_percent)
        )

    # TODO: Добавить проверку на минимальную цену по рекомендованной цене

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


def get_ya_data_for_order(order: dict, tariffs_dict: dict, plan_margin: float = 28.0):
    margin = round(plan_margin / 100, 3)
    article = order.get('article', '')
    article_data = tariffs_dict.get(article, {})
    if not article_data:
        print(f'Артикул {article} - нет в группе ЯндексМаркет в базе МС, добавлен в отчет с нулевыми значениями')
        return {
            "order_number": order.get("order_number", ""),
            "created": order.get("created", ""),
            "quantity": order.get("quantity", 0.0),
            "name": 'Нет данных в МС',
            "article": article,
            "stock": 0.0,
            "price": 0.0,
            "recommended_price": 0.0,
            "prime_cost": 0.0,
            "commission": 0.0,
            "acquiring": 0.0,
            "delivery": 0.0,
            "crossregional_delivery": 0.0,
            "sorting": 0.0,
            "profit": 0.0,
            "profitability": 0.0,
        }
    article_data = tariffs_dict[article]
    price = order.get("price", 0.0)
    prime_cost = article_data.get("PRIME_COST", 0.0)

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
    sorting = article_data.get("SORTING", 0.0)

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
