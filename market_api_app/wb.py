from datetime import datetime
import logging
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('WB')


class WB(ApiBase):
    def __init__(self, api_key: str):
        super().__init__()
        self.headers = {'Authorization': api_key, 'Content-Type': 'application/json'}
        self.domain = 'wildberries.ru'
        self.host = f'https://marketplace-api.{self.domain}/'

    def get_commission(self):
        logger.info(f'Получение комиссий по категориям')
        url = f'https://common-api.{self.domain}/api/v1/tariffs/commission'
        result = self.get(url, {'locale': 'ru'})
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о комиссиях.')
        return response_json

    def get_tariffs_for_box(self):
        logger.info(f'Получение данных логистики')
        url = f'https://common-api.{self.domain}/api/v1/tariffs/box'
        current_date = datetime.now().strftime('%Y-%m-%d')
        params = {'date': current_date}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о тарифах логистики.')
        return response_json

    def get_product_prices(self):
        print(f'Получение актуальных цен и дисконта')
        url = f'https://discounts-prices-api.{self.domain}/api/v2/list/goods/filter'
        params = {'limit': 1000, 'offset': 0}

        products_list = []
        while True:
            result = self.get(url, params)
            if result:
                response_json = result.json()
                list_goods = response_json.get('data', {}).get('listGoods', [])
                if list_goods:
                    products_list += list_goods
                    params['offset'] += params['limit']
                else:
                    break
            else:
                logger.error('Не удалось получить данные о ценах.')
                break
        return products_list

    def get_orders(self, from_data):
        url = f'https://statistics-api.{self.domain}/api/v1/supplier/orders'
        params = {'dateFrom': from_data, 'flag': 1}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о заказах.')
        return response_json

    def get_sales(self, from_data):
        url = f'https://statistics-api.{self.domain}/api/v1/supplier/sales'
        params = {'dateFrom': from_data, 'flag': 1}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о заказах.')
        return response_json

    def get_orders_fbs(self, from_date=None, to_date=None):
        url = self.host + 'api/v3/orders'
        params = {'limit': 1000, 'next': 0}
        if from_date:
            params['dateFrom'] = from_date
        if to_date:
            params['dateTo'] = to_date

        orders_fbs = []
        while True:
            result = self.get(url, params)
            if result:
                response_json = result.json()
                orders_list = response_json.get('orders')
                next_cursor = response_json.get('next')
                if orders_list and next_cursor:
                    orders_fbs += orders_list
                    params['next'] = next_cursor
                else:
                    break
            else:
                logger.error('Не удалось получить данные о заказах FBS.')
                break
        return orders_fbs

    def get_offices(self):
        url = f'https://marketplace-api.{self.domain}/api/v3/offices'
        result = self.get(url)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о складах.')
        return response_json

    def get_stocks_report(self, from_date="2025-09-15", to_date="2025-09-15", nm_ids=None) -> dict:
        if nm_ids is None:
            nm_ids = []
        url = f'https://seller-analytics-api.{self.domain}/api/v2/stocks-report/offices'
        params = {
            "nmIDs": nm_ids,
            "currentPeriod": {
                "start": from_date,
                "end": to_date
            },
            "stockType": "",
            "skipDeletedNm": False
        }
        result = self.post(url, params)
        response_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить данные об остатках.')
        return response_json

    def get_stocks_report_for_products(self, from_date="2025-11-20", to_date="2025-11-20", nm_ids=None) -> dict:
        if nm_ids is None:
            nm_ids = []
        url = f'https://seller-analytics-api.{self.domain}/api/v2/stocks-report/products/products'
        params = {
            'nmIDs': nm_ids,
            'currentPeriod': {
                'start': from_date,
                'end': to_date
            },
            'stockType': '',
            'skipDeletedNm': False,
            'orderBy': {
                'field': 'stockCount',  # Сортировка по остаткам на текущий день
                'mode': 'desc'  # Убыванию
            },
            'availabilityFilters': [
                'deficient',
                'actual',
                'balanced',
                'nonActual',
                'nonLiquid',
                'invalidData'
            ],
            'limit': 1000,
            'offset': 0
        }

        products_stocks = []
        while True:
            result = self.post(url, params)
            if result:
                response_json = result.json()
                products_list = response_json.get('data', {}).get('items', [])
                if products_list and len(products_list) <= 1000:
                    products_stocks += products_list
                    params['offset'] += 1000
                else:
                    break
            else:
                logger.error('Не удалось получить данные об остатках')
                break

        return {int(prod.get('nmID')): prod.get('metrics') for prod in products_stocks if prod.get('nmID')}

    def get_stocks_for_nm_id(self, nm_id: int, from_date: str = '2025-11-20', to_date: str = '2025-11-20') -> list:

        url = f'https://seller-analytics-api.{self.domain}/api/v2/stocks-report/products/sizes'
        params = {
            'nmID': nm_id,
            'currentPeriod': {
                'start': from_date,
                'end': to_date
            },
            'stockType': '',
            'orderBy': {
                'field': 'stockCount',  # Сортировка по остаткам на текущий день
                'mode': 'desc'  # Убыванию
            },
            'includeOffice': True
        }

        result = self.post(url, params)
        response_json = result.json() if result else {}
        if not result:
            logger.error('Не удалось получить данные об остатках.')
        # Можно дописать разбор остатка из офисов
        stocks_offices = response_json.get('data', {}).get('offices', [])
        return stocks_offices

    def get_stocks(self, from_date: str = '2025-11-01T00:00:00'):
        url = f'https://statistics-api.{self.domain}/api/v1/supplier/stocks'
        params = {'dateFrom': from_date}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о складах.')
        return response_json
