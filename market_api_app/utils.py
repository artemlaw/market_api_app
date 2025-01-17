import os
from datetime import datetime, timedelta


def in_colab() -> bool:
    try:
        from google.colab import userdata
        return True
    except ImportError:
        return False


# TODO: Переделать функцию для частичного получения ключей по потребности c опциями ms, wb, ym, ozon
def get_api_tokens() -> (str, str, str, str, str):
    try:
        from google.colab import userdata
        try:
            MS_API_TOKEN = userdata.get("MS_API_TOKEN")
            WB_API_TOKEN = userdata.get("WB_API_TOKEN")
            YM_API_TOKEN = userdata.get("YM_API_TOKEN")
            OZ_CLIENT_ID = userdata.get("OZ_CLIENT_ID")
            OZ_API_TOKEN = userdata.get("OZ_API_TOKEN")
            return MS_API_TOKEN, WB_API_TOKEN, YM_API_TOKEN, OZ_CLIENT_ID, OZ_API_TOKEN
        except KeyError:
            pass
    except ImportError:
        pass
    from dotenv import load_dotenv

    load_dotenv()
    MS_API_TOKEN = os.getenv("MS_API_TOKEN")
    WB_API_TOKEN = os.getenv("WB_API_TOKEN")
    YM_API_TOKEN = os.getenv("YM_API_TOKEN")
    OZ_CLIENT_ID = os.getenv("OZ_CLIENT_ID")
    OZ_API_TOKEN = os.getenv("OZ_API_TOKEN")

    return MS_API_TOKEN, WB_API_TOKEN, YM_API_TOKEN, OZ_CLIENT_ID, OZ_API_TOKEN


def get_ya_ids():
    try:
        from google.colab import userdata
        try:
            fbs_campaign_id = userdata.get("YA_FBS_CAMPAIGN_ID")
            ex_campaign_id = userdata.get("YA_EXPRESS_CAMPAIGN_ID")
            business_id = userdata.get("YA_BUSINESS_ID")
            return fbs_campaign_id, ex_campaign_id, business_id
        except KeyError:
            pass
    except ImportError:
        pass
    from dotenv import load_dotenv

    load_dotenv()
    fbs_campaign_id = os.getenv("YA_FBS_CAMPAIGN_ID")
    ex_campaign_id = os.getenv("YA_EXPRESS_CAMPAIGN_ID")
    business_id = os.getenv("YA_BUSINESS_ID")

    return fbs_campaign_id, ex_campaign_id, business_id


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


if __name__ == '__main__':
    dates = get_date_for_request('2024-08-30', '2024-09-01')
    print(dates)
