import logging
import requests
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('API')


class ApiBase:
    def __init__(self, max_retries: int = 3, delay_seconds: int = 10):
        self.headers = {'Content-Type': 'application/json'}
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds

    @staticmethod
    def raise_for_status_(response):
        if response.status_code == 404:
            logger.warning(f"Warning: 404 Error encountered. URL: {response.url}")
            return
        response.raise_for_status()

    def handle_request_errors(self, func, *args, **kwargs):
        for attempt in range(self.max_retries):
            try:
                response = func(*args, **kwargs)
                self.raise_for_status_(response)
                return response
            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    logger.debug(e.response)
                    logger.error(f'Неудачный запрос, ошибка: {e}. Повтор через {self.delay_seconds} секунд.')
                    time.sleep(self.delay_seconds)
                else:
                    logger.error(
                        f'Достигнуто максимальное количество попыток ({self.max_retries}). '
                        f'Прекращение повторных запросов.')
        return None

    def get(self, url, params=None):
        return self.handle_request_errors(self._get, url, params=params)

    def post(self, url, data):
        return self.handle_request_errors(self._post, url, json=data)

    def put(self, url, data):
        return self.handle_request_errors(self._put, url, json=data)

    def delete(self, url):
        return self.handle_request_errors(self._delete, url)

    def _get(self, url, params=None):
        return requests.get(url, headers=self.headers, params=params)

    def _post(self, url, json):
        return requests.post(url, headers=self.headers, json=json)

    def _put(self, url, json):
        return requests.put(url, headers=self.headers, json=json)

    def _delete(self, url):
        return requests.delete(url, headers=self.headers)
