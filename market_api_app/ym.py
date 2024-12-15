import logging

from market_api_app.utils import get_ya_ids, get_value_by_name
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('YaMarket')

# Константа можно вынести в перспективе в файл настроек модуля
transit_warehouse_type = "MINI_SORTING_CENTER"  # Склад сортировки. Определяет стоимость обработки


class YaMarket(ApiBase):
    def __init__(self, api_key: str, max_retries: int = 3, delay_seconds: int = 15):
        super().__init__(max_retries=max_retries, delay_seconds=delay_seconds)
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.host = "https://api.partner.market.yandex.ru/"

    def get_campaigns(self):
        logger.info(f"Получение информации о магазинах кабинета")
        url = self.host + "campaigns?page=&pageSize="
        result = self.get(url)
        response_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить данные о комиссиях.')
        return response_json

    def get_categories(self, offers: list, campaign_id: int = 0, selling_program: str = "FBS"):
        logger.info(f"Получение актуальных тарифов")
        # Максимум 200, то можно совместить с получением номенклатуры
        url = self.host + "tariffs/calculate"
        data = {
            "parameters": {
                "frequency": "BIWEEKLY",
                "campaignId" if campaign_id else "sellingProgram": campaign_id
                or selling_program,
            },
            "offers": offers,
        }
        result = self.post(url, data)
        if not result:
            logger.error("Не удалось получить данные о карточках товара.")
        result_json = result.json() if result else {}
        if result_json and result_json.get("status") == "OK":
            return result_json.get("result", {}).get("offers", [])
        else:
            logger.error("Не удалось получить данные о карточках товара.")
            return []

    def get_offers(self, business_id: int):
        logger.info(f"Получение карточек товара")
        page_token = ""
        data = {"archived": False}

        offers_list = []
        while True:
            url = (
                self.host
                + f"businesses/{business_id}/offer-mappings?page_token={page_token}&limit=200"
            )
            result = self.post(url, data)
            result_json = result.json() if result else {}
            if result_json and result_json.get("status") == "OK":
                offers_list += result_json.get("result", {}).get("offerMappings", [])
                if not result_json.get("result", {}).get("paging", {}):
                    break
                page_token = (
                    result_json.get("result", {}).get("paging", {}).get("nextPageToken", "")
                )
            else:
                logger.error("Не удалось получить данные о карточках товара.")
                break
        return offers_list

    def get_orders(self, campaign_id: int = 0, from_date: str = '13-12-2024', to_date: str = '13-12-2024') -> list:
        logger.info(f"Получение информации о заказах")
        url = self.host + f'campaigns/{campaign_id}/orders'
        params = {'fake': False, 'fromDate': from_date, 'toDate': to_date, 'limit': 1000}
        orders_list = []
        while True:
            result = self.get(url, params)
            result_json = result.json() if result else {}
            if result_json and result_json.get("orders"):
                orders_list += result_json.get("orders")
                if not result_json.get("paging", {}):
                    break
                params['page_token'] = result_json.get("paging", {}).get("nextPageToken", "")
            else:
                logger.error("Не удалось получить данные о заказах.")
                break
        return orders_list


def get_ya_campaign_and_business_ids(ym_client: YaMarket, fbs: bool = True):
    ids = get_ya_ids()
    campaign_id, business_id = (ids[0], ids[2]) if fbs else (ids[1], ids[2])

    if campaign_id and business_id:
        return campaign_id, business_id
    else:
        campaigns = ym_client.get_campaigns()
        campaign = campaigns.get("campaigns", [])[0]
        campaign_id = int(campaign.get("id"))
        business_id = int(campaign.get("business", {}).get("id"))
        return campaign_id, business_id


def chunked_offers_list(func, ym_client, campaign_id, data: list, chunk_size: int = 200):
    result = {}
    for i in range(0, len(data), chunk_size):
        chunk_data = data[i: i + chunk_size]
        result = {**result, **func(ym_client, campaign_id, chunk_data)}
    return result


def get_dict_for_commission(ym_client: YaMarket, campaign_id: int, offers: list) -> dict:
    if len(offers) > 200:
        logger.error("Ограничение запроса комиссии! Не более 200 товаров")
        offers = offers[:200]
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

    commission = ym_client.get_categories(
        campaign_id=campaign_id, offers=offers_data
    )
    # print(len(commission))

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

    # TODO: Добавить проверку на прибыль по рекомендованной цене

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
