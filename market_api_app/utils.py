import os
import json
from datetime import datetime, timedelta
from types import ModuleType
from market_api_app.version import __version__


def in_colab() -> bool | ModuleType:
    print(f'Integration module v.{__version__}')
    try:
        from google.colab import userdata
        return userdata
    except ImportError:
        return False


def get_api_keys(keys: list) -> tuple:
    """
    Получение ключей из userdata в colab либо из .env
    :param keys: ["MS_API_TOKEN", "WB_API_TOKEN", "OZ_CLIENT_ID", "OZ_API_TOKEN",
                "YM_API_TOKEN", "YA_FBS_CAMPAIGN_ID", "YA_EXPRESS_CAMPAIGN_ID", "YA_BUSINESS_ID"]
    :return:
    """
    userdata = in_colab()
    if not userdata:
        from dotenv import load_dotenv
        load_dotenv()
    tokens = [userdata.get(key) if userdata else os.getenv(key) for key in keys]
    return tuple(tokens)


def create_code_index(elements: list) -> dict:
    code_index = {}
    for element in elements:
        code = int(element.get('code'))
        if code:
            code_index[code] = element
    return code_index


def get_value_by_name(elements, name):
    return next((element["value"] for element in elements if element["name"] == name), None)


def get_date_for_request(start_date_str: str, end_date_str: str) -> tuple[tuple, int, int]:
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

    from_date_for_fbs = int(start_date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    if start_date == end_date:
        return (start_date_str,), from_date_for_fbs, int(
            start_date.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())

    from_date_for_fbo = tuple(
        (start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((end_date - start_date).days + 1))

    to_date_for_fbs = int(end_date.replace(hour=23, minute=59, second=59, microsecond=999999).timestamp())

    return from_date_for_fbo, from_date_for_fbs, to_date_for_fbs


def date_to_utc(date_str: str, start_of_day: bool = True) -> str:
    """
    Принимает строку в формате '15.12.2024' и возвращает строку в формате UTC: '2024-12-15T00:00:00Z'
    или '2024-12-15T23:59:59Z'
    """
    date_ = datetime.strptime(date_str, '%d-%m-%Y')
    if start_of_day:
        date_ = date_.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        date_ = date_.replace(hour=23, minute=59, second=59, microsecond=999999)
    return date_.isoformat() + 'Z'


def format_date(date_str: str) -> str:
    """
    Принимает дату в формате 'YYYY-MM-DD' и возвращает её в формате 'DD-MM-YYYY'
    """
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d-%m-%Y')


def get_current_datetime(str_format: str = '%Y-%m-%d %H:%M:%S') -> str:
    return datetime.now().strftime(str_format)


def dict_to_json_file(data: dict, file_path: str):
    """Принимает словарь и записывает его в файл json.

    :param data: Словарь, который будет записан в файл.
    :param file_path: Путь к файлу, в который будет записан словарь.
    """
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, separators=(',', ':'), ensure_ascii=False)


def add_regions_sum_immutable(data_dict: dict, target_regions: list) -> dict:
    """
    Создает новый словарь с добавленными суммами регионов.
    Не изменяет исходный словарь.

    :param data_dict: Словарь, исходный из get_stocks_wh.
    :param target_regions: Список наименований складов по которым суммировать остаток в 'Регионы'
    """
    result = {}

    for key, value in data_dict.items():
        a, b, items_list = value
        total_region_sum = 0
        # Суммируем значения для целевых регионов
        for item in items_list:
            for region_name, region_value in item.items():
                if region_name in target_regions:
                    total_region_sum += region_value

        # Создаем новый список с добавленной записью
        modified_items = items_list + [{'Регионы': total_region_sum}]
        # Создаем новый кортеж
        result[key] = (a, b, modified_items)

    return result


if __name__ == '__main__':
    # dates = get_date_for_request('2024-08-30', '2024-09-01')
    # print(dates)
    a = in_colab()
    print(a)
