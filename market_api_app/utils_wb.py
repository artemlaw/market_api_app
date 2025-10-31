import time
from market_api_app import WB
from market_api_app.utils import get_date_for_request

FBS_COMMISSION = 0.0  # Принудительное повышение комиссии FBS на 0.0% над FBO, так как нет по API


def find_warehouse_by_name(warehouses: list, name: str) -> dict | None:
    return next((warehouse for warehouse in warehouses if warehouse['warehouseName'] == name), None)


def get_logistic_dict(tariffs_data: dict, warehouse_name: str = 'Маркетплейс: Центральный федеральный округ',
                      fbs: bool = False) -> dict:
    tariff = find_warehouse_by_name(warehouses=tariffs_data['response']['data']['warehouseList'], name=warehouse_name)
    if not tariff:
        tariff = find_warehouse_by_name(warehouses=tariffs_data['response']['data']['warehouseList'], name='Коледино')

    # boxDeliveryBase, boxDeliveryMarketplaceBase - Логистика, первый литр, ₽
    # boxDeliveryLiter, boxDeliveryMarketplaceLiter - Логистика, дополнительный литр, ₽
    # boxDeliveryCoefExpr, boxDeliveryMarketplaceCoefExpr - Коэффициент Логистика, %.
    # На него умножается стоимость логистики. Уже учтён в тарифах

    # Применение fbs для подтягивания тарифа FBS по складу FBW
    logistics_first_liter = tariff['boxDeliveryBase'] \
        if tariff['boxDeliveryBase'] != '-' or not fbs else tariff['boxDeliveryMarketplaceBase']
    logistics_extra_liter = tariff['boxDeliveryLiter'] \
        if tariff['boxDeliveryLiter'] != '-' or not fbs else tariff['boxDeliveryMarketplaceLiter']
    logistics_coefficient = tariff['boxDeliveryCoefExpr'] \
        if tariff['boxDeliveryCoefExpr'] != '-' or not fbs else tariff['boxDeliveryMarketplaceCoefExpr']

    # Вырезать показатели после изменения использования метода
    # tariff_for_base_l = tariff['boxDeliveryBase'] \
    #     if tariff['boxDeliveryBase'] != '-' else tariff['boxDeliveryMarketplaceBase']
    # tariff_over_base = tariff['boxDeliveryLiter'] \
    #     if tariff['boxDeliveryLiter'] != '-' else tariff['boxDeliveryMarketplaceLiter']
    # wb_coefficient = tariff['boxDeliveryCoefExpr'] \
    #     if tariff['boxDeliveryCoefExpr'] != '-' else tariff['boxDeliveryMarketplaceCoefExpr']

    # Логистика
    logistic_dict = {
        'KTR': 1.0,
        'TARIFF_BASE': 1.0,
        # 'TARIFF_FOR_BASE_L': float(tariff_for_base_l.replace(',', '.')),
        # 'TARIFF_OVER_BASE': float(tariff_over_base.replace(',', '.')),
        # 'WH_COEFFICIENT': round(float(wb_coefficient.replace(',', '.')) / 100, 2),
        'LOGISTICS_FIRST_LITER': float(logistics_first_liter.replace(',', '.')),
        'LOGISTICS_EXTRA_LITER': float(logistics_extra_liter.replace(',', '.')),
        'LOGISTICS_COEFFICIENT': round(float(logistics_coefficient.replace(',', '.')) / 100, 2)
    }
    return logistic_dict


def get_category_dict(wb_client: WB) -> dict:
    commission = wb_client.get_commission()
    return {comm['subjectName']: (comm['kgvpMarketplace'], comm['paidStorageKgvp']) for comm in commission['report']}


def get_price_dict(wb_client: WB) -> dict:
    product_prices = wb_client.get_product_prices()
    # Если несколько размеров, то берет максимальную цену и дисконт
    price_dict = {d['nmID']: {
        'price': max(s['discountedPrice'] for s in d['sizes']),
        'discount': d['discount']
    } for d in product_prices}

    return price_dict


def create_prices_dict(prices_list: list) -> dict:
    prices_dict = {}
    for price in prices_list:
        name = price['priceType']['name']
        value = price['value']
        prices_dict[name] = value
    return prices_dict


def get_logistics(ktr: float, tariff_for_base_l: float, tariff_base: float, tariff_over_base: float,
                  wh_coefficient: float, volume: float) -> float:
    volume_calc = max(volume - tariff_base, 0)
    # Коэффициент логистики склада wh_coefficient стал в показателях уже применен
    wh_coefficient = 1.0
    logistics = round((tariff_for_base_l * tariff_base + tariff_over_base * volume_calc) * wh_coefficient * ktr, 2)
    return logistics


def get_logistics_for_one_liter(ktr: float, logistics_first_liter: float, logistics_extra_liter: float, volume: float) -> float:
    volume_calc = max(volume - 1, 0)
    return round((logistics_first_liter + logistics_extra_liter * volume_calc) * ktr, 2)


# TODO: WB - Проверять на актуальность расчет логистики
def get_logistics_new(ktr: float, logistics_coefficient: float, logistics_first_liter: float,
                      logistics_extra_liter: float, volume: float) -> float:
    """
    Тариф на логистику
    от 0,001 до 0,200 литра — 23₽ за литр;
    от 0,201 до 0,400 литра — 26₽ за литр;
    от 0,401 до 0,600 литра — 29₽ за литр;
    от 0,601 до 0,800 литра — 30₽ за литр;
    от 0,801 до 1,000 литра — 32₽ за литр.

    Для товаров с объёмом более 1 литра:
    стоимость первого литра 46₽,
    стоимость каждого дополнительного литра 14₽.
    """
    volume_steps = [
        (0.001, 0.200, 23.0),
        (0.201, 0.400, 26.0),
        (0.401, 0.600, 29.0),
        (0.601, 0.800, 30.0),
        (0.801, 0.999, 32.0)
    ]

    if volume > 1.0:
        return get_logistics_for_one_liter(ktr, logistics_first_liter, logistics_extra_liter, volume)

    for min_vol, max_vol, value in volume_steps:
        if min_vol <= volume <= max_vol:
            return value * logistics_coefficient

    return logistics_first_liter


# TODO: WB - Проверять на актуальность расчет рекомендуемой цены
def calculate_recommended_price(prime_cost: float, logistics: float, plan_margin: float,
                                commission: float, acquiring: float = 1.6, min_price: float = 60.0) -> float:
    # Преобразуем проценты в доли
    plan_margin /= 100
    acquiring /= 100
    commission /= 100
    recom_price = round((prime_cost + logistics) / (1 - plan_margin - commission - acquiring), 0)
    if recom_price < min_price:
        recom_price = min_price
    return recom_price


def get_wb_data_for_article(nm_id: int, product: dict, prices_dict: dict, category_dict: dict, logistic_dict: dict,
                            plan_margin, acquiring: float = 1.5, fbs: bool = True, card_stocks: bool = False) -> dict:
    price = float(prices_dict.get('price', 0))
    discount = float(prices_dict.get('discount', 0))
    prime_cost = product.get('PRIME_COST', 0.0)
    category = product.get('CATEGORY', '')
    volume = product.get('VOLUME', 0.0)

    commissions = category_dict.get(category)
    if not commissions:
        print(
            f"У товара {nm_id} не заполнена категория или категория'{category}' отсутствует в словаре,"
            f" необходимо обновить данные в Мой склад")
        commission = 30.0
    else:
        commission = commissions[0] + FBS_COMMISSION if fbs else commissions[1]

    # logistics = get_logistics(logistic_dict['KTR'], logistic_dict['TARIFF_FOR_BASE_L'], logistic_dict['TARIFF_BASE'],
    #                           logistic_dict['TARIFF_OVER_BASE'], logistic_dict['WH_COEFFICIENT'], volume)
    logistics = get_logistics_new(ktr=logistic_dict['KTR'], volume=volume,
                                  logistics_coefficient=logistic_dict['LOGISTICS_COEFFICIENT'],
                                  logistics_first_liter=logistic_dict['LOGISTICS_FIRST_LITER'],
                                  logistics_extra_liter=logistic_dict['LOGISTICS_EXTRA_LITER'])

    commission_cost = round(commission / 100 * price, 1)
    acquiring_cost = round(acquiring / 100 * price, 1)

    reward = round(commission_cost + acquiring_cost + logistics, 1)
    profit = round(price - prime_cost - reward, 1)
    if price == 0:
        profitability = 0
    else:
        profitability = round(profit / price * 100, 1)

    recommended_price = calculate_recommended_price(prime_cost, logistics, plan_margin, commission, acquiring)

    data = {
        'name': product.get('NAME', ''),
        'article': product.get('ARTICLE', ''),
        'nm_id': nm_id,
        'url': f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx',
        'stock': product.get('STOCK', 0.0),
        'discount': discount,
        'price': price,
        'recommended_price': recommended_price,
        'prime_cost': prime_cost,
        'commission': commission_cost,
        'acquiring': acquiring_cost,
        'logistics': logistics,
        'profit': profit,
        'profitability': profitability
    }
    if card_stocks:
        data = {
            'name': product.get('NAME', ''),
            'article': product.get('ARTICLE', ''),
            'nm_id': nm_id,
            'url': f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx',
            'stock': product.get('STOCK', 0.0),
            'stock_fbs': product.get('STOCK_FBS', 0),
            'stock_fbo': product.get('STOCK_FBO', 0),
            'discount': discount,
            'price': price,
            'recommended_price': recommended_price,
            'prime_cost': prime_cost,
            'commission': commission_cost,
            'acquiring': acquiring_cost,
            'logistics': logistics,
            'profit': profit,
            'profitability': profitability
        }

    return data


def get_order_data(order: dict, product: dict, base_dict: dict, plan_margin: float, acquiring: float = 1.5,
                   fbs: bool = True) -> dict:
    wb_prices_dict = base_dict['wb_prices_dict']
    if fbs:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'], warehouse_name='Маркетплейс: Центральный '
                                                                                    'федеральный округ', fbs=True)
    else:
        logistic_dict = get_logistic_dict(base_dict['tariffs_data'],
                                          warehouse_name=order.get('warehouseName', 'Подольск'))

    nm_id = order.get('nmId', '')
    # if nm_id == 008011159:
    #     print('Test')
    # Получение цены
    price = float(wb_prices_dict.get(nm_id, {}).get('price', 0.0))
    if not price:
        price = round(order.get('finishedPrice', 0.0), 1)

    # Получение скидки
    discount = float(wb_prices_dict.get(nm_id, {}).get('discount', 0))
    if not discount:
        discount = order.get('discountPercent', 0)
    # Себестоимость
    prime_cost = product.get('PRIME_COST', 0.0)
    order_price = round(order.get('finishedPrice', 0.0), 1)

    category = product.get('CATEGORY', '')
    commissions = base_dict.get('category_dict', {}).get(category)
    if not commissions:
        print(f'Не удалось определить комиссию для {nm_id} по категории {category} по умолчанию указал 30%')
        commission = 30.0
    else:
        commission = commissions[0] + FBS_COMMISSION if fbs else commissions[1]

    volume = product.get('VOLUME', 0.0)
    # logistics = get_logistics(logistic_dict['KTR'], logistic_dict['TARIFF_FOR_BASE_L'], logistic_dict['TARIFF_BASE'],
    #                           logistic_dict['TARIFF_OVER_BASE'], logistic_dict['WH_COEFFICIENT'], volume)
    logistics = get_logistics_new(ktr=logistic_dict['KTR'], volume=volume,
                                  logistics_coefficient=logistic_dict['LOGISTICS_COEFFICIENT'],
                                  logistics_first_liter=logistic_dict['LOGISTICS_FIRST_LITER'],
                                  logistics_extra_liter=logistic_dict['LOGISTICS_EXTRA_LITER'])

    commission_cost = round(commission / 100 * price, 1)
    acquiring_cost = round(acquiring / 100 * price, 1)

    reward = round(commission_cost + acquiring_cost + logistics, 1)
    profit = round(price - prime_cost - reward, 1)
    profitability = round(profit / price * 100, 1)

    recommended_price = calculate_recommended_price(prime_cost, logistics, plan_margin, commission, acquiring)

    order_commission_cost = round(commission / 100 * order_price, 1)
    order_acquiring_cost = round(acquiring / 100 * order_price, 1)

    order_reward = round(order_commission_cost + order_acquiring_cost + logistics, 1)
    order_profit = round(order_price - prime_cost - order_reward, 1)
    order_profitability = round(order_profit / order_price * 100, 1)

    model = 'FBS_' if fbs else 'FBO_'

    data = {
        'name': product.get('NAME', ''),
        'article': product.get('ARTICLE', ''),
        'nm_id': nm_id,
        'url': f'https://www.wildberries.ru/catalog/{nm_id}/detail.aspx',
        'stock': product.get('STOCK', 0.0),
        'stock_fbs': product.get('STOCK_FBS', 0),
        'stock_fbo': product.get('STOCK_FBO', 0),
        'order_create': order.get('date', ''),
        'order_name': model + order.get('sticker', '0'),
        'quantity': 1,
        'discount': discount,
        'price': price,
        'order_price': order_price,
        'recommended_price': recommended_price,
        'prime_cost': prime_cost,
        'commission': commission_cost,
        'acquiring': acquiring_cost,
        'logistics': logistics,
        'profit': profit,
        'profitability': profitability,
        'order_profit': order_profit,
        'order_profitability': order_profitability
    }

    return data


def wb_get_orders(wb_client: WB, start_of_day: str, end_of_day: str):
    fbo_tuple_from_date, from_date_for_fbs, to_date_for_fbs = get_date_for_request(start_of_day, end_of_day)
    wb_orders = []
    total_dates = len(fbo_tuple_from_date)
    for i, from_date in enumerate(fbo_tuple_from_date):
        wb_orders.extend(wb_client.get_orders(from_date))
        if i < total_dates - 1:
            time.sleep(20)

    # Запас +/- 3ч - 10800( 6ч - 21600)
    wb_orders_fbs = wb_client.get_orders_fbs(from_date=from_date_for_fbs - 10800, to_date=to_date_for_fbs + 10800)
    rids = {order_fbs.get('rid') for order_fbs in wb_orders_fbs}

    orders_fbs_cancel = []
    orders_fbo_cancel = []
    orders_fbs = []
    orders_fbo = []
    nm_ids_fbs = []
    nm_ids_fbo = []

    for order in wb_orders:
        srid = order.get('srid')
        # order_type = order.get('orderType')
        is_cancel = order.get('isCancel')

        # if order_type == 'Клиентский' and not is_cancel:
        if not is_cancel:
            if order.get('srid') in rids:
                orders_fbs.append(order)
                nm_ids_fbs.append(order.get('nmId'))
            else:
                orders_fbo.append(order)
                nm_ids_fbo.append(order.get('nmId'))
        else:
            if srid in rids:
                orders_fbs_cancel.append(order)
            else:
                orders_fbo_cancel.append(order)

    print(f"{'Модель':<15}{'Количество':<10}")
    print('-' * 25)
    print(f"{'FBS':<15}{len(orders_fbs):<10}")
    print(f"{'FBS отмены':<15}{len(orders_fbs_cancel):<10}")
    print(f"{'FBO':<15}{len(orders_fbo):<10}")
    print(f"{'FBO отмены':<15}{len(orders_fbo_cancel):<10}")
    print('-' * 25)
    print(f"{'Всего заказов':<15}{len(wb_orders):<10}")
    print(f"{'Без отмены':<15}{len(wb_orders) - len(orders_fbs_cancel) - len(orders_fbo_cancel):<10}")

    return orders_fbs, orders_fbo, set(nm_ids_fbs), set(nm_ids_fbo)


if __name__ == '__main__':
    test_volumes = [0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0, 1.5]
    for vol in test_volumes:
        logistics_vol = get_logistics_new(ktr=1.0, logistics_coefficient=1.0, logistics_first_liter=46.0,
                                          logistics_extra_liter=14.0, volume=vol)
        print(f'Объем: {vol}л -> Тариф: {logistics_vol}₽')
