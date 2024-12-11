from datetime import datetime
import logging
from market_api_app.base import ApiBase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('WB')


class WB(ApiBase):
    def __init__(self, api_key: str):
        super().__init__()
        self.headers = {'Authorization': api_key, 'Content-Type': 'application/json'}
        self.host = 'https://marketplace-api.wildberries.ru/'

    def get_commission(self):
        logger.info(f'Получение комиссий по категориям')
        url = 'https://common-api.wildberries.ru/api/v1/tariffs/commission'
        result = self.get(url, {'locale': 'ru'})
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о комиссиях.')
        return response_json

    def get_tariffs_for_box(self):
        logger.info(f'Получение данных логистики')
        url = 'https://common-api.wildberries.ru/api/v1/tariffs/box'
        current_date = datetime.now().strftime('%Y-%m-%d')
        params = {'date': current_date}
        result = self.get(url, params)
        response_json = result.json() if result else []
        if not result:
            logger.error('Не удалось получить данные о тарифах логистики.')
        return response_json

    def get_product_prices(self):
        print(f'Получение актуальных цен и дисконта')
        url = 'https://discounts-prices-api.wb.ru/api/v2/list/goods/filter'
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
        url = 'https://statistics-api.wildberries.ru/api/v1/supplier/orders'
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
