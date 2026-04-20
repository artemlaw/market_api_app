import os
import json
import time
from datetime import datetime, timedelta
from types import ModuleType
from typing import Union, Dict, List, Any, Optional
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


class JSONStorage:
    """
    Класс для работы с JSON-файлом с поддержкой временных меток
    """

    def __init__(self, filename: str = 'temp_storage.json', max_age_hours: int = 24):
        """
        Args:
            filename: имя JSON-файла для хранения данных
            max_age_hours: максимальный возраст данных в часах
        """
        self.filename = filename
        self.max_age_hours = max_age_hours

    def write_data(self, db: Union[Dict, List]) -> bool:
        """
        Записывает данные в JSON-файл с временной меткой

        Args:
            db: словарь или список для сохранения

        Returns:
            bool: True если запись успешна, иначе False
        """
        try:
            storage_data = {
                "data": db,
                "timestamp": datetime.now().isoformat(),
                "timestamp_unix": time.time(),
            }

            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, separators=(',', ':'), ensure_ascii=False)
            print(f"✅ Данные записаны в {self.filename}")
            return True

        except Exception as e:
            print(f"❌ Ошибка при записи данных: {e}")
            return False

    def is_data_fresh(self) -> bool:
        """
        Проверяет, не устарели ли данные (время фиксации меньше max_age_hours)

        Returns:
            bool: True если данные свежие, False если устарели или файла нет
        """
        try:
            # Проверяем существование файла и возраст данных
            with open(self.filename, 'r', encoding='utf-8') as f:
                storage_data = json.load(f)
                timestamp_unix = storage_data.get("timestamp_unix")
                if timestamp_unix and (time.time() - timestamp_unix) < self.max_age_hours * 3600:
                    return True
                else:
                    return False

        except FileNotFoundError:
            print(f"⚠️ Файл {self.filename} не существует")
            return False
        except Exception as e:
            print(f"❌ Ошибка при проверке свежести данных: {e}")
            return False

    def clear_file(self) -> bool:
        """
        Очищает файл (удаляет содержимое)

        Returns:
            bool: True если очистка успешна, иначе False
        """
        try:
            # Записываем пустые данные
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=4)

            print(f"🧹 Файл {self.filename} успешно очищен")
            return True

        except Exception as e:
            print(f"❌ Ошибка при очистке файла: {e}")
            return False

    def read_data(self) -> Optional[Union[Dict, List, Any]]:
        """
        Получить данные из файла

        Returns:
            Данные из файла (dictionary, list or None if error)
        """
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                storage_data = json.load(f)
                timestamp_unix = storage_data.get("timestamp_unix")
                if timestamp_unix and (time.time() - timestamp_unix) < self.max_age_hours * 3600:
                    return storage_data.get("data")
                else:
                    return None
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        except Exception as e:
            print(f"❌ Ошибка при чтении файла: {e}")
            return None


if __name__ == '__main__':
    # dates = get_date_for_request('2024-08-30', '2024-09-01')
    # print(dates)
    a = in_colab()
    print(a)

    # Создаем экземпляр класса (данные старше 2 часов считаются устаревшими)
    storage = JSONStorage(filename="my_storage.json", max_age_hours=1)

    print("=" * 50)
    print("ПРИМЕР 1: Запись словаря")
    print("=" * 50)

    # Записываем словарь
    my_dict = {
        "name": "Мой проект",
        "version": 1.0,
        "status": "active",
        "settings": {
            "theme": "dark",
            "notifications": True
        }
    }
    storage.write_data(my_dict)

    print("\n" + "=" * 50)
    print("ПРИМЕР 2: Чтение данных")
    print("=" * 50)

    # Читаем данные
    data = storage.read_data()
    print(f"Прочитанные данные: {data}")

    print("\n" + "=" * 50)
    print("ПРИМЕР 3: Проверка свежести данных")
    print("=" * 50)

    # Проверяем свежесть
    is_fresh = storage.is_data_fresh()
    print(f"Данные свежие: {is_fresh}")

    print("\n" + "=" * 50)
    print("ПРИМЕР 4: Запись списка")
    print("=" * 50)

    # Записываем список
    my_list = [1, 2, 3, 4, 5, "текст", {"ключ": "значение"}]
    storage.write_data(my_list)

    # Читаем список
    list_data = storage.read_data()
    print(f"Прочитанный список: {list_data}")

    print("\n" + "=" * 50)
    print("ПРИМЕР 5: Очистка файла")
    print("=" * 50)

    # Очищаем файл
    storage.clear_file()

    # Пытаемся прочитать после очистки
    empty_data = storage.read_data()
    print(f"Данные после очистки: {empty_data}")
