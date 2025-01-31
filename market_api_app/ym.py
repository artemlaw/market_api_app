import logging
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('YaMarket')


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

    def get_tree(self):
        logger.info(f"Получение информации о категориях")
        url = self.host + "categories/tree"
        data = {
          "language": "RU"
        }
        result = self.post(url, data)
        if not result:
            logger.error("Не удалось получить данные о категориях товара.")
        result_json = result.json() if result else {}
        if result_json and result_json.get("status") == "OK":
            return result_json.get("result", {}).get("children", [])
        else:
            logger.error("Не удалось получить данные о категориях товара.")
            return []
