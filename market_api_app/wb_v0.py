# Формирование отчета Рентабельность WB
import re
import pandas as pd
from market_api_app import MoySklad, WB, get_api_keys
from market_api_app.utils_wb import (get_logistic_dict, get_price_dict, get_category_dict, create_prices_dict,
                                     get_logistics_new)
from market_api_app.utils_ms import get_attributes_dict, get_volume
from market_api_app.tabstyle import TabStyles

WAREHOUSE_NAME = 'Маркетплейс: Центральный федеральный округ'

'''
Использовать в Colab в виде:
import ipywidgets as widgets
from datetime import datetime, timedelta
from IPython.display import display
from google.colab import files

from market_api_app import get_first_report_data, get_wb_first_report

# Эквайринг
ACQUIRING = 1.6  # в %

ms_client, first_report_data = get_first_report_data()

to_date = datetime.now().date()
# Получаем вчерашний день (from_date)
from_date = to_date - timedelta(days=1)

# Создаем текстовое поле для ввода даты и времени
from_input = widgets.Text(
    description='Период с:',
    placeholder='YYYY-MM-DD HH:MM',
    value=f'{from_date} 18:00'
)

to_input = widgets.Text(
    description='до:',
    placeholder='YYYY-MM-DD HH:MM',
    value=f'{to_date} 23:59'
)

# Отображаем виджет
display(from_input)
display(to_input)

# Функция для получения значения после ввода и проверки формата
def get_datetime():
    from_input_value = from_input.value
    to_input_value = to_input.value
    try:
        # Проверяем корректность формата даты и времени
        from_date = datetime.strptime(from_input_value, '%Y-%m-%d %H:%M')
        to_date = datetime.strptime(to_input_value, '%Y-%m-%d %H:%M')
        from_date_f = f'{from_date}.000'
        to_date_f = f'{to_date}.000'
        report = get_wb_first_report(ms_client=ms_client, base_dict_=first_report_data, 
                            from_date_=from_date_f, to_date_=to_date_f, 
                            acquiring=ACQUIRING)
        files.download(report)
    except ValueError:
        print("Пожалуйста, введите корректную дату и время в формате YYYY-MM-DD HH:MM.")

# Кнопка для подтверждения ввода
button = widgets.Button(description="Сформировать отчет", button_style='info')
button.on_click(lambda b: get_datetime())
display(button)
'''


def get_product_id_from_url(url):
    pattern = r'/product/([0-9a-fA-F-]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    else:
        return None


def get_stock_for_bundle(stocks_dict, product):
    product_bundles = product['components']['rows']
    product_stock = 0.0
    for bundle in product_bundles:
        bundle_id = get_product_id_from_url(bundle['assortment']['meta']['href'])
        if bundle_id in stocks_dict.keys():
            p_stock = stocks_dict[bundle_id] // bundle['quantity']
            if p_stock > product_stock:
                product_stock = p_stock
    return product_stock


def get_wb_stocks_dict(ms_client):
    print('Получение остатков номенклатуры')
    stocks = ms_client.get_stock()
    # Получить остатки основной номенклатуры
    stocks_dict = {stock['assortmentId']: stock['quantity'] for stock in stocks}
    products = ms_client.get_bundles()  # Получить комплекты
    wb_stocks_dict = {product['code']: get_stock_for_bundle(stocks_dict, product) for product in products}
    return wb_stocks_dict


def get_dict_for_report(ms_client, wb_client):
    wb_stocks_dict = get_wb_stocks_dict(ms_client)
    category_dict = get_category_dict(wb_client)
    tariffs_data = wb_client.get_tariffs_for_box()
    logistic_dict = get_logistic_dict(tariffs_data, WAREHOUSE_NAME, fbs=True)
    wb_prices_dict = get_price_dict(wb_client)
    return {
        'wb_stocks_dict': wb_stocks_dict,
        'category_dict': category_dict,
        'logistic_dict': logistic_dict,
        'wb_prices_dict': wb_prices_dict
    }


def get_order_data(order: dict, base_dict: dict, acquiring: float = 1.6):
    stocks_dict = base_dict['wb_stocks_dict']
    logistic_dict = base_dict['logistic_dict']
    wb_prices_dict = base_dict['wb_prices_dict']

    position = order['positions']['rows'][0]
    nm_id = int(position['assortment']['code'])
    sale_prices = position['assortment']['salePrices']
    prices_dict = create_prices_dict(sale_prices)

    # Получение цены
    price = float(wb_prices_dict.get(nm_id, {}).get('price', 0.0))
    if not price:
        price = prices_dict.get('Цена WB после скидки', 0) / 100

    # Получение скидки
    discount = float(wb_prices_dict.get(nm_id, {}).get('discount', 0))
    if not discount:
        price_before_discount = prices_dict.get('Цена WB до скидки', 0)
        price_after_discount = prices_dict.get('Цена WB после скидки', 0)
        if price_before_discount:
            discount = (1 - round(price_after_discount / price_before_discount, 1)) * 100
        else:
            discount = 0

    cost_price_c = prices_dict['Цена основная']
    cost_price = cost_price_c / 100
    order_price = order['sum'] / 100

    attributes = position['assortment']['attributes']
    attributes_dict = get_attributes_dict(attributes)
    volume = get_volume(attributes_dict)

    logistics = get_logistics_new(ktr=logistic_dict['KTR'], volume=volume,
                                  logistics_coefficient=logistic_dict['LOGISTICS_COEFFICIENT'],
                                  logistics_first_liter=logistic_dict['LOGISTICS_FIRST_LITER'],
                                  logistics_extra_liter=logistic_dict['LOGISTICS_EXTRA_LITER'])

    category = attributes_dict.get('Категория товара', '')
    commissions = base_dict.get('category_dict', {}).get(category)
    if not commissions:
        print(f'Не удалось определить комиссию для {nm_id} по категории {category} по умолчанию указал 30%')
        commission = 30.0
    else:
        commission = commissions[0]

    commission_cost = round(commission / 100 * price, 1)
    acquiring_cost = round(acquiring / 100 * price, 1)

    reward = round(commission_cost + acquiring_cost + logistics, 1)
    profit = round(price - cost_price - reward, 1)
    profitability = round(profit / price * 100, 1)

    order_commission_cost = round(commission / 100 * order_price, 1)
    order_acquiring_cost = round(acquiring / 100 * order_price, 1)

    order_reward = round(order_commission_cost + order_acquiring_cost + logistics, 1)
    order_profit = round(order_price - cost_price - order_reward, 1)
    order_profitability = round(order_profit / order_price * 100, 1)

    data = {
        'name': position.get('assortment', {}).get('name', ''),
        'nm_id': nm_id,
        'article': position.get('assortment', {}).get('article', ''),
        'stock': stocks_dict.get(nm_id, 0),
        'order_create': order.get('moment'),
        'order_name': order.get('name'),
        'quantity': position.get('quantity', 1),
        'discount': discount,
        'item_price': price,
        'order_price': order_price,
        'cost_price': cost_price,
        'commission': commission_cost,
        'acquiring': acquiring_cost,
        'logistics': logistics,
        'reward': reward,
        'profit': profit,
        'profitability': profitability,
        'order_reward': order_reward,
        'order_profit': order_profit,
        'order_profitability': order_profitability
    }

    return data


def get_wb_first_report(ms_client, base_dict_, from_date_, to_date_, acquiring: float = 1.6):
    print(f'Формирую отчет по заказам от {from_date_} до {to_date_}')
    filter_str = f'?filter=moment>{from_date_};moment<{to_date_};&order=name,desc&expand=positions.assortment,state'
    orders = ms_client.get_orders(filter_str=filter_str)
    orders_for_report = [get_order_data(order, base_dict_, acquiring) for order in orders
                         if 'Отменен' not in order['state']['name']]
    print('Количество заказов исключая отмены:', len(orders_for_report))
    path_xls_file = 'wb_рентабельность.xlsx'
    if orders_for_report:
        pd.set_option('display.max_columns', None)
        df = pd.DataFrame(orders_for_report)
        # Возможно убрать и не хранить общую таблицу
        df.to_excel(path_xls_file, sheet_name='Список', index=False)
        total_df = df.groupby('name').agg({
            'stock': 'min',
            'quantity': 'sum',
            'discount': 'max',
            'item_price': 'sum',
            'order_price': 'sum',
            'cost_price': 'sum',
            'commission': 'sum',
            'acquiring': 'sum',
            'logistics': 'sum',
            'reward': 'sum',
            'profit': 'sum',
            'order_reward': 'sum',
            'order_profit': 'sum'
        }).reset_index()
        # Рассчитать profitability
        total_df['profitability'] = round((total_df['profit'] / total_df['item_price']) * 100, 1)
        total_df['order_profitability'] = round((total_df['order_profit'] / total_df['order_price']) * 100, 1)
        total_df = pd.concat([total_df, pd.DataFrame(columns=['order_name', 'order_create', 'nm_id', 'article'])])

        overall_totals = df.agg({
            'stock': 'sum',
            'quantity': 'sum',
            'item_price': 'sum',
            'order_price': 'sum',
            'cost_price': 'sum',
            'commission': 'sum',
            'acquiring': 'sum',
            'logistics': 'sum',
            'reward': 'sum',
            'profit': 'sum',
            'order_reward': 'sum',
            'order_profit': 'sum'
        }).to_frame().T

        overall_totals['name'] = 'Итог'
        overall_totals['profitability'] = round((overall_totals['profit'] / overall_totals['item_price']) * 100, 1)
        overall_totals['order_profitability'] = round(
            (overall_totals['order_profit'] / overall_totals['order_price']) * 100, 1)
        overall_totals = overall_totals[['name', 'stock', 'quantity', 'item_price', 'order_price', 'cost_price',
                                         'commission', 'acquiring', 'logistics', 'reward', 'profit', 'profitability',
                                         'order_reward', 'order_profit', 'order_profitability']]
        # Определите желаемый порядок столбцов для объединенного DataFrame
        desired_column_order = ['name', 'nm_id', 'article', 'order_name', 'order_create', 'stock', 'quantity',
                                'discount', 'item_price', 'order_price', 'cost_price', 'commission', 'acquiring',
                                'logistics', 'reward', 'profit', 'profitability', 'order_reward', 'order_profit',
                                'order_profitability']
        # Объедините DataFrame с учетом столбцов в желаемом порядке и сортируя по name и order_name
        cascade_table = pd.concat([total_df[desired_column_order], df[desired_column_order]]) \
            .sort_values(by=['name', 'order_name']).reset_index(drop=True)

        cascade_table.loc[-1] = overall_totals.iloc[0]
        cascade_table.index = cascade_table.index + 1
        cascade_table = cascade_table.sort_index()

        tab_styles = TabStyles()

        with pd.ExcelWriter(path_xls_file, engine='openpyxl', mode='a') as writer:
            cascade_table.to_excel(writer, sheet_name='Сводная', index=False)

            wb = writer.book
            ws = wb['Сводная']
            # Установите ширину по умолчанию для всех столбцов (например, 15)
            ws.sheet_format.defaultColWidth = 10
            # Установите ширину для определенных столбцов
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['C'].width = 15
            ws.column_dimensions['D'].width = 12

            columns_to_align_right = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

            for row in range(2, ws.max_row + 1):
                order_name_cell = ws.cell(row=row, column=2)  # Столбец 'order_name' - второй столбец
                if order_name_cell.value:  # Если значение ячейки не пустое
                    for cell in ws[row]:
                        cell.style = tab_styles.row_l2_style
                    ws.row_dimensions[row].outline_level = 1
                    ws.row_dimensions.group(start=row, end=row, hidden=True)
                    ws.cell(row=row, column=17).style = tab_styles.col_spec_style
                    ws.cell(row=row, column=20).style = tab_styles.col_spec_style
                else:
                    for cell in ws[row]:
                        cell.style = tab_styles.row_l1_style
                    ws.cell(row=row, column=17).style = tab_styles.cell_l1_spec_style
                    ws.cell(row=row, column=20).style = tab_styles.cell_l1_spec_style

                for col in columns_to_align_right:
                    ws.cell(row=row, column=col).alignment = tab_styles.columns_to_align_right
                    ws.cell(row=row, column=col).number_format = '#,##0.0'  # Формат с одним знаком после запятой

            new_header = [
                'Наименование', 'NmID', 'Артикул', 'Заказ', 'Дата заказа', 'Остаток', 'Кол-во', 'Дисконт',
                'Цена товара', 'Цена заказа', 'Себест-ть', 'Комиссия', 'Эквайринг', 'Логистика', 'Вознагр-ние',
                'Прибыль', 'Рент-ть', 'Вознагр-ние за заказ', 'Прибыль за заказ', 'Рент-ть заказа'
            ]
            # Заменяем значения и определяем стиль в заголовке (первой строке)
            for i, value in enumerate(new_header):
                cell = ws.cell(row=1, column=i + 1)
                cell.value = value
                cell.style = tab_styles.header_row_spec_style if i in [16, 19] else tab_styles.header_row_style

                results_cell = ws.cell(row=2, column=i + 1)
                results_cell.style = tab_styles.header_row_spec_style

            # Автофильтры
            ws.auto_filter.ref = ws.dimensions
            # Зафиксировать ячейки
            ws.freeze_panes = 'B3'

        print('Файл отчета готов')
    else:
        print('На указанный интервал нет данных для отчета')
    return path_xls_file


def get_first_report_data():
    ms_token, wb_token = get_api_keys(["MS_API_TOKEN", "WB_API_TOKEN"])
    ms_client = MoySklad(ms_token)
    wb_client = WB(api_key=wb_token)
    return ms_client, get_dict_for_report(ms_client, wb_client)
