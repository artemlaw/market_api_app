from gspread import Client, Spreadsheet, service_account, service_account_from_dict
from typing import List, Dict


def client_init_json(file_path: str) -> Client:
    """Создание клиента для работы с Google Sheets."""
    return service_account(filename=file_path)


def client_init_dict(service_account_dict: dict) -> Client:
    """Создание клиента для работы с Google Sheets."""
    return service_account_from_dict(service_account_dict)


def get_table_by_url(client: Client, table_url):
    """Получение таблицы из Google Sheets по ссылке."""
    return client.open_by_url(table_url)


def get_table_by_id(client: Client, table_url):
    """Получение таблицы из Google Sheets по ID таблицы."""
    return client.open_by_key(table_url)


def get_worksheet_info(table: Spreadsheet) -> dict:
    """Возвращает количество листов в таблице и их названия."""
    worksheets = table.worksheets()
    worksheet_info = {
        "count": len(worksheets),
        "names": [worksheet.title for worksheet in worksheets]
    }
    return worksheet_info


def extract_data_from_sheet(table: Spreadsheet, sheet_name: str) -> List[Dict]:
    """
    Извлекает данные из указанного листа таблицы Google Sheets и возвращает список словарей.

    :param table: Объект таблицы Google Sheets (Spreadsheet).
    :param sheet_name: Название листа в таблице.
    :return: Список словарей, представляющих данные из таблицы.
    """
    worksheet = table.worksheet(sheet_name)
    return worksheet.get_all_records()


def get_column_values_by_index(table: Spreadsheet, sheet_name: str, column_index: int) -> List[str]:
    """Возвращает значения столбца по индексу.

    :param table: Объект таблицы Google Sheets (Spreadsheet).
    :param sheet_name: Название листа в таблице.
    :param column_index: Индекс столбца.
    :return: Список значений столбца.
    """
    worksheet = table.worksheet(sheet_name)
    column_values = worksheet.col_values(column_index)

    return column_values[1:]


def get_table(access_file_or_dict: str | dict, table_key: str):
    """Получения таблицы из Google Sheets."""
    if isinstance(access_file_or_dict, dict):
        client = client_init_dict(access_file_or_dict)
    else:
        client = client_init_json(access_file_or_dict)
    # client = client_init_dict(file_path)
    if table_key.startswith('https'):
        table = get_table_by_url(client, table_key)
    else:
        table = get_table_by_id(client, table_key)
    return table


if __name__ == '__main__':
    table_link = 'https://docs.google.com/spreadsheets/d/_________'
    table_id = '_________'
    file_settings = 'wb-tabs.json'

    wb_table = get_table(file_settings, table_id)
    nm_ids = get_column_values_by_index(wb_table, 'ОПТ ', 4)


