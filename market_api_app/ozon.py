import logging
from market_api_app.utils import date_to_utc
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Ozon')


class Ozon(ApiBase):
    def __init__(self, client_id: str, api_key: str, max_retries: int = 3, delay_seconds: int = 15):
        super().__init__(max_retries=max_retries, delay_seconds=delay_seconds)
        self.headers = {
            "Api-Key": api_key,
            "Client-Id": client_id,
            "Content-Type": "application/json",
        }
        self.host = "https://api-seller.ozon.ru/"

    def get_products_info(self, product_id: list):
        # logger.info(f"Получение детальной информации по товарам")
        url = self.host + "v2/product/info/list"
        data = {"product_id": product_id}
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по товарам.')
        return result_json.get("result", {}).get("items", [])

    def get_products_info_v3(self, product_id: list):
        # logger.info(f"Получение детальной информации по товарам")
        url = self.host + "v3/product/info/list"
        data = {"product_id": product_id}
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по товарам.')
        return result_json.get("items", [])

    def get_prices(self, product_id: list):
        logger.info(f"Получение данных по тарифам")
        url = self.host + "v5/product/info/prices"
        data = {
            "cursor": "",
            "filter": {
                "product_id": product_id,
                "visibility": "ALL"
            },
            "limit": 1000
        }
        result = self.post(url, data)
        prices_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по тарифам.')
        return prices_json.get("items", [])

    def get_products(self):
        logger.info(f"Получение данных по товарах")
        url = self.host + "v3/product/list"
        limit = 1000
        data = {
            "filter": {
                "offer_id": [],
                "product_id": [],
                "visibility": "ALL"
            },
            "last_id": "",
            "limit": limit
        }

        offers_list = []
        total = limit
        while True:
            result = self.post(url, data)
            result_json = result.json() if result else {}
            if result_json and result_json.get("result"):
                products_ = result_json.get("result", {}).get("items", [])
                products_ids = [product['product_id'] for product in products_ if not product['archived']]
                products_info = self.get_prices(product_id=products_ids)
                offers_list += products_info
                if result_json.get("result", {}).get("total", 0) < total:
                    break
                data["last_id"] = result_json.get("result", {}).get("last_id", "")
                total += limit
            else:
                logger.error("Не удалось получить данные о товарах.")
                break
        return offers_list

    def get_products_v2(self):
        logger.info(f"Получение данных по товарах")
        url = self.host + "v3/product/list"
        limit = 1000
        data = {
            "filter": {
                "offer_id": [],
                "product_id": [],
                "visibility": "ALL"
            },
            "last_id": "",
            "limit": limit
        }

        offers_list = []
        total = limit
        while True:
            result = self.post(url, data)
            result_json = result.json() if result else {}
            if result_json and result_json.get("result"):
                products_ = result_json.get("result", {}).get("items", [])
                products_ids = [product['product_id'] for product in products_ if not product['archived']]
                products_info = self.get_products_info_v3(product_id=products_ids)
                offers_list += products_info
                total_full = result_json.get("result", {}).get("total", 0)
                logger.info(f"Всего товаров: {total_full}, осталось: {total_full - len(offers_list)}")
                if total_full < total:
                    break
                data["last_id"] = result_json.get("result", {}).get("last_id", "")
                total += limit
            else:
                logger.error("Не удалось получить данные о товарах.")
                break
        return offers_list

    def get_orders(self, from_date, to_date):
        logger.info(f"Получение информации о заказах")
        url = self.host + "v3/posting/fbs/list"
        since = date_to_utc(from_date)
        to = date_to_utc(to_date, start_of_day=False)
        data = {
            "dir": "ASC",
            "filter": {
                "is_quantum": False,
                "since": since,
                "to": to
            },
            "limit": 1000,
            "offset": 0,
            "with": {
                "analytics_data": False,
                "barcodes": False,
                "financial_data": True,
                "translit": False
            }
        }
        result = self.post(url, data)
        result_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить информацию по заказам.')
        return result_json.get("result", {}).get("postings", [])
