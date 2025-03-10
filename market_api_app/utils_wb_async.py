import asyncio
import aiohttp
import platform
import pandas as pd
import numpy as np
import logging

from market_api_app import get_api_keys, MoySklad, ExcelStyle
from market_api_app.utils_ms import get_ms_products_for_wb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('WB FBO')


def get_stocks_info(sizes):
    fbs_stock = 0
    fbo_stock = 0

    for size in sizes:
        stocks = size.get('stocks')
        for stock in stocks:
            wh_id = stock.get('wh')
            if wh_id == 119261:
                fbs_stock += stock.get('qty')
            else:
                fbo_stock += stock.get('qty')

    return fbs_stock, fbo_stock


async def get_data(session, url, headers, params, max_retries=5, delay_seconds=30):
    for attempt in range(1, max_retries + 1):
        try:
            async with session.get(url=url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.info(
                        f'Неудачный запрос, статус: {response.status}. Повтор через {delay_seconds} секунд.')
                    await asyncio.sleep(delay_seconds)
        except aiohttp.ClientError as e:
            logger.info(f'Ошибка при отправке запроса на {url}: {e}')
            await asyncio.sleep(delay_seconds)

    logger.info(f'Достигнуто максимальное количество попыток ({max_retries}). Прекращение повторных запросов.')
    return None


async def get_cards_detail(nm_ids: str):

    url = 'https://card.wb.ru/cards/v2/detail'

    headers = {
        'Accept': '*/*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/134.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="134", "Google Chrome";v="134", "Not:A-Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"'
    }

    params = {
        'curr': 'rub',
        'dest': '-1257786',
        'appType': '1',
        'spp': '30',
        'nm': nm_ids,
    }
    try:
        async with aiohttp.ClientSession() as session:
            products = []
            result = await get_data(session, url=url, headers=headers, params=params)
            if result:
                products = result.get('data').get('products')
                return products
            else:
                return products

    except aiohttp.ClientError as e:
        print(f'Произошла ошибка при выполнении запроса: {e}')


async def get_cards_async(nn_list: list, max_portion=100):
    tasks = []

    for i in range(0, len(nn_list), max_portion):
        portion = ';'.join(map(str, nn_list[i:i + max_portion]))
        task = asyncio.create_task(get_cards_detail(portion))
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    all_products = [product for result in results if result for product in result]
    return all_products


async def get_wb_fbo_stock():
    update_data = []
    ms_token = get_api_keys(["MS_API_TOKEN"])[0]
    ms_client = MoySklad(api_key=ms_token)

    ms_wb_products = get_ms_products_for_wb(ms_client)
    nn_list = list(ms_wb_products.keys())

    logger.info(f'Исход: {len(nn_list)}')
    products = await get_cards_async(nn_list)
    print('WB: Получение остатка по товарам FBO')
    logger.info(f'Результат: {len(products)}')

    for prod in products:
        fbs_stock, fbo_stock = get_stocks_info(prod.get('sizes'))

        if fbo_stock:
            nm_id = prod.get('id')
            web_url = f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx'
            cost_one = ms_wb_products[nm_id].get('PRIME_COST', 0.0)
            product_name = ms_wb_products[nm_id].get('NAME', 'БЕЗ ИМЕНИ')
            cost_full = fbo_stock * cost_one
            # if fbs_stock > 0:
            #     print(f'{nm_id} - FBS {fbs_stock} - FBO {fbo_stock}')
            update_data.append([product_name, nm_id, web_url, cost_one, fbo_stock, cost_full])

    if update_data:
        # Заголовки столбцов
        columns = ['Наименование', 'nm_id', 'Ссылка', 'Себестоимость', 'FBO остаток', 'Полная себестоимость']
        df = pd.DataFrame(update_data, columns=columns)
        # df = pd.DataFrame(update_data)
        df.loc['Итого'] = df[['Себестоимость', 'FBO остаток', 'Полная себестоимость']].sum()
        df.loc['Итого', ['Наименование', 'nm_id', 'Ссылка']] = ['Итого', np.nan, '']

        path_xls_file = 'wb_fbo_stock.xlsx'
        style = ExcelStyle()
        style.style_dataframe(df, path_xls_file, "Остаток FBO")
        print("Файл отчета готов")
        return path_xls_file


if __name__ == '__main__':
    async def main():
        if platform.system() == 'Windows':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        await get_wb_fbo_stock()

    asyncio.run(main())
