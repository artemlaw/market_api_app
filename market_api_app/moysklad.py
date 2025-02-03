import logging
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MoySklad')


class MoySklad(ApiBase):
    def __init__(self, api_key: str):
        super().__init__()
        self.headers = {'Accept-Encoding': 'gzip', 'Authorization': api_key, 'Content-Type': 'application/json'}
        self.host = 'https://api.moysklad.ru/api/remap/1.2/'

    def fetch_data(self, url, params):
        items = []
        while True:
            result = self.get(url, params)
            if result:
                response_json = result.json()
                items += response_json.get('rows', [])
                params['offset'] += params['limit']
                if response_json.get('meta', {}).get('size', 0) < params['offset']:
                    break
            else:
                break
        return items

    def get_products_list(self):
        url = f'{self.host}entity/product'
        params = {'limit': 1000, 'offset': 0}
        return self.fetch_data(url, params)

    def update_product(self, product):
        url = f'{self.host}entity/product/{product.get("id")}'

        result = self.put(url, data=product)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось обновить номенклатуру.')
        return response_json

    def get_bundles(self):
        url = f'{self.host}entity/bundle?expand=components.rows.assortment'
        params = {'limit': 100, 'offset': 0}
        return self.fetch_data(url, params)

    def update_bundle(self, bundle):
        url = f'{self.host}entity/bundle/{bundle.get("id")}'
        result = self.put(url, data=bundle)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось обновить товар.')
        return response_json

    def get_label(self, product_id, product_type='bundle', count=1):
        url = f'{self.host}entity/{product_type}/{product_id}/export/'
        # Формируется на основе данных аккаунта
        data = {
            "organization": {
                "meta": {
                    "href": "https://api.moysklad.ru/api/remap/1.2/entity/organization/"
                            "29310743-0c62-11ef-0a80-1736000feae2",
                    "metadataHref": "https://api.moysklad.ru/api/remap/1.2/entity/organization/metadata",
                    "type": "organization",
                    "mediaType": "application/json",
                    "uuidHref": "https://online.moysklad.ru/app/#mycompany/edit?id=29310743-0c62-11ef-0a80-1736000feae2"
                }
            },
            "count": count,
            "salePrice": {
                "priceType": {
                    "meta": {
                        "href": "https://api.moysklad.ru/api/remap/1.2/context/companysettings/pricetype/"
                                "2933628a-0c62-11ef-0a80-1736000feaeb",
                        "type": "pricetype",
                        "mediaType": "application/json"
                    }
                }
            },
            "template": {
                "meta": {
                    "href": "https://api.moysklad.ru/api/remap/1.2/entity/assortment/metadata/customtemplate/"
                            "d01825c6-7377-415b-8db4-f99b8dbd1fb4",
                    "type": "embeddedtemplate",
                    "mediaType": "application/json"
                }
            }
        }
        result = self.post(url, data=data)
        if result:
            response_content = result.content
        else:
            response_content = ''
            logger.error('Не удалось получить этикетку.')
        return response_content

    def get_stock_all(self):
        url = f'{self.host}report/stock/all'
        params = {'limit': 1000, 'offset': 0}
        stocks_list = self.fetch_data(url, params)
        logger.info(f'Получен остаток по номенклатуре: {len(stocks_list)}')
        return stocks_list

    def get_stock(self):
        url = f'{self.host}report/stock/all/current'
        # 'include': 'zeroLines' - показать товары с нулевым доступным остатком
        params = {'stockType': 'quantity', 'include': 'zeroLines'}  # по умолчанию params = {'stockType': 'quantity'}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о наличии.')
        return response_json

    def get_orders(self, filter_str):
        # Пример:
        # from_date_f = f'{from_date} 00:00:00.000'
        # to_date_f = f'{to_date} 23:59:00.000'
        # filter_str = f'?filter=moment>{from_date};moment<{to_date};&order=name,desc&expand=positions.assortment,state'
        url = f'{self.host}entity/customerorder{filter_str}'
        params = {'limit': 100, 'offset': 0}
        return self.fetch_data(url, params)

    def create_registration(self):
        # TODO: Реализовать метод создания оприходования
        url = f'{self.host}entity/enter'
        data = {
            "organization": {},
            "store": {}
        }
        result = self.post(url, data=data)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось создать Оприходование товара.')
        return response_json
