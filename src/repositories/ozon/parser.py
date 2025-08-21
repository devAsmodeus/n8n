import re
import asyncio
import aiohttp
import uuid
import json

from aiogram import Bot
from datetime import datetime
from collections import defaultdict
from typing import Optional, Any
from bs4 import BeautifulSoup

from src.database import async_session_maker
from src.models.ozon import (
    SearchMatchOrm,
    UrlProductsOrm,
    ProductTopOrm,
    ProductCharacteristicsOrm
)
from src.utils import retry_decorators, log_decorators

from sqlalchemy import select, insert, delete


async def send_product_data(
        bot: Bot,
        chat_id: int,
        product_url: str,
        sorting_type: str
) -> None:
    messages = list()
    headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_name, sku_id = await get_product_name(session, product_url)
        if product_name:
            messages.append(product_name)
            exists_flag, unique_id = await check_exists(product_name, sorting_type)
            if exists_flag:
                if products := await get_products(session, product_name, sorting_type):
                    products = await format_products(session, products, sorting_type)
                    await upload_products(product_url, product_name, sku_id, products)
                    messages.extend(await format_message(products))
                else:
                    messages.append("Товары не найдены")
            else:
                db_info = await get_database_info(unique_id, sorting_type)
                messages.extend(await format_message(db_info))
        else:
            messages.append("Наименование не распознано")

        for message in messages:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML"
                )
            except Exception as exception:
                print(repr(exception))
                await bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
            await asyncio.sleep(1.5)


async def format_message(
        products: dict[str, Any]
) -> list[str]:
    result = list()
    result.append(products['message'])

    if products.get('details', dict()).get('products'):
        group_message = "<b>Товары</b>:\n"
        for index, url in enumerate(products.get('details', dict()).get('products', list())[:5], start=1):
            group_message += f'<a href="{url}">Товар {index}</a>\n'
        else:
            result.append(group_message)

    if products.get('details', dict()).get('main_image'):
        result.append((
            f'<a href="{products.get("details", dict()).get("main_image")}">'
            f'Изображение самого популярного товара</a>'
        ))

    if products.get('details', dict()).get('description'):
        result.append((
            f'<b>Описание самого популярного товара</b>:\n'
            f"<i>{products.get('details', dict()).get('description', str())[:4_000]}</i>"
        ))

    if products.get('details', dict()).get('characteristics'):
        group_message = "<b>Характеристики</b>:\n"
        for index, (key, value) in enumerate(
                products.get('details', dict()).get('characteristics', dict()).items(), start=1
        ):
            if index <= 7:
                if value is None:
                    value = ""
                elif isinstance(value, list):
                    value = "; ".join(value)
                else:
                    value = str(value)

                group_message += f"<b>{key}</b>: <i>{value}</i>\n"
        else:
            result.append(group_message)

    if products.get('details', dict()).get('currency_price'):
        group_message = "Стоимость:\n"
        for key, value in products.get('details', dict()).get('currency_price', dict()).items():
            key = {
                'avg_price': "Средняя цена",
                'max_price': "Максимальная цена",
                'min_price': "Минимальная цена"
            }[key]
            group_message += f'<b>{key}</b>: <i>{value}</i>\n'
        else:
            result.append(group_message)

    return result


async def get_product_data(
        product_url: str,
        sorting_type: str
) -> dict[str, Any]:
    headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_name, sku_id = await get_product_name(session, product_url)
        if product_name:
            exists_flag, unique_id = await check_exists(product_name)
            if exists_flag:
                if products := await get_products(session, product_name, sorting_type):
                    products = await format_products(session, products, sorting_type)
                    return await upload_products(product_url, product_name, sku_id, products)
                else:
                    return dict(
                        sorting_type=sorting_type,
                        message="Товары не найдены",
                        details=dict()
                    )
            else:
                return await get_database_info(unique_id, sorting_type)
        else:
            return dict(
                sorting_type=sorting_type,
                message="Наименование не распознано",
                details=dict()
            )


async def get_database_info(
        unique_id: uuid.UUID,
        sorting_type: str
) -> dict[str, Any]:
    result = dict(
        sorting_type=sorting_type,
        message="Выгрузка с базы данных",
        details=dict(
            products=list(),
            main_image=None,
            characteristics=dict(),
            description=None,
            currency_price=dict()
        )
    )
    async with async_session_maker() as db_session:
        query = select(UrlProductsOrm).filter_by(unique_id=unique_id, sorting_type=sorting_type)
        urls = await db_session.execute(query)
        urls = urls.scalars().fetchall()

        query = select(ProductTopOrm).filter_by(unique_id=unique_id)
        product = await db_session.execute(query)
        product = product.scalars().fetchall()

        query = select(ProductCharacteristicsOrm).filter_by(unique_id=unique_id)
        characteristics = await db_session.execute(query)
        characteristics = characteristics.scalars().fetchall()

    result["details"]["products"] = [url.product_url for url in urls]

    for row in product:
        match row.attribute_name:
            case "avg_price" | "max_price" | "min_price":
                result["details"]["currency_price"][row.attribute_name] = float(row.value)
            case _:
                result["details"][row.attribute_name] = row.value

    for row in characteristics:
        result["details"]["characteristics"][row.characteristics_name] = eval(row.value)

    return result


async def upload_products(
        product_url: str,
        product_name: str,
        sku_id: int,
        products: dict[str, Any]
) -> dict[str, Any]:
    match_values = {
        "unique_id": (new_uuid := uuid.uuid4()),
        "product_url": product_url,
        "sku_id": sku_id,
        "concat_name": product_name,
        "create_time": datetime.now(),
        "update_time": datetime.now(),
        "sorting_type": products.get('sorting_type', 'score')
    }

    urls_values = [
        {
            "unique_id": new_uuid,
            "sorting_type": products.get('sorting_type', 'score'),
            "index": index,
            "product_url": url
        }
        for index, url in enumerate(products.get('details', dict()).get('products', list()), start=1)
    ]

    product_values = [
        {
            "unique_id": new_uuid,
            "attribute_name": key,
            "value": str(value)
        }
        for key, value in products.get('details', dict()).get('currency_price', dict()).items()
    ]
    product_values.extend([
        {
            "unique_id": new_uuid,
            "attribute_name": key,
            "value": products.get('details', dict()).get(key)
        }
        for key in ('main_image', 'description')
    ])

    characteristics_values = [
        {
            "unique_id": new_uuid,
            "characteristics_name": key,
            "value": str(value)
        }
        for key, value in products.get('details', dict()).get('characteristics', dict()).items()
    ]

    async with async_session_maker() as db_session:
        insert_match_stmt = insert(SearchMatchOrm).values(**match_values)
        await db_session.execute(insert_match_stmt)
        insert_urls_stmt = insert(UrlProductsOrm).values(urls_values)
        await db_session.execute(insert_urls_stmt)
        insert_product_stmt = insert(ProductTopOrm).values(product_values)
        await db_session.execute(insert_product_stmt)
        insert_characteristics_stmt = insert(ProductCharacteristicsOrm).values(characteristics_values)
        await db_session.execute(insert_characteristics_stmt)

        await db_session.commit()

    return products


async def check_exists(
        product_name: str,
        sorting_type: str
) -> tuple[bool, uuid.UUID | None]:
    async with async_session_maker() as db_session:
        query = select(SearchMatchOrm)
        matches = await db_session.execute(query)
        matches = {
            (match.concat_name, match.sorting_type): {
                'unique_id': match.unique_id,
                'update_time': match.update_time
            }
            for match in matches.scalars().fetchall()
        }

    if (product_name, sorting_type) in matches:
        unique_id = matches[(product_name, sorting_type)]['unique_id']
        update_time = matches[(product_name, sorting_type)]['update_time']
        if (datetime.now() - update_time).days <= 7:
            return False, unique_id
        else:
            async with async_session_maker() as db_session:
                delete_urls_stmt = (
                    delete(SearchMatchOrm)
                    .where(SearchMatchOrm.unique_id == unique_id)
                )
                await db_session.execute(delete_urls_stmt)
                await db_session.commit()

            return True, None
    else:
        return True, None


async def format_products(
        session: aiohttp.ClientSession,
        products: dict[str, Any],
        sorting_type: str
) -> dict:
    result = dict(products=[
        'https://www.ozon.ru' + product.get('action', dict()).get('link')
        for product in products.get('products', list())
    ])

    for product in products.get('product_top', list()):
        result['main_image'] = await get_main_image(product)
        details = await parse_details(session, product.get('sku'))
        for name, value in json.loads(details).get('widgetStates', dict()).items():
            if name.startswith('webCharacteristics-') and value != '{}':
                result['characteristics'] = await get_characteristics(json.loads(value))
            if name.startswith('webDescription-') and value != '{}':
                if 'richAnnotationType' in (description := json.loads(value)):
                    if description.get('richAnnotationType') == 'HTML':
                        result['description'] = description.get('richAnnotation', '')
                    else:
                        result['description'] = 'Rich-Content'

    for section in products.get('filters', dict()).get('sections', list()):
        for filter_ in section.get('filters', list()):
            if filter_.get('key') == 'currency_price':
                filter_data = filter_.get('multipleRangesFilter', dict()).get('rangeFilter', dict())
                min_value = float(filter_data.get('minValue', '0'))
                max_value = float(filter_data.get('maxValue', '0'))
                result['currency_price'] = {
                    'min_price': min_value,
                    'max_price': max_value,
                    'avg_price': round((min_value + max_value) / 2, 2)
                }

    return dict(
        sorting_type=sorting_type,
        message="Новая выгрузка",
        details=result
    )


async def get_characteristics(
        data: dict[str, Any]
) -> dict:
    result = defaultdict(list)
    for part_data in data.get('characteristics', list()):
        for _, characteristics in part_data.items():
            if isinstance(characteristics, list):
                for characteristic in characteristics:
                    characteristic_name = characteristic.get('name', '')
                    for value in characteristic.get('values', list()):
                        result[characteristic_name].append(value.get('text', ''))
    else:
        return result


async def get_main_image(
        product: dict[str, Any]
) -> Optional[str]:
    for item in product.get('tileImage', dict()).get('items', list()):
        return item.get('image', dict()).get('link')
    else:
        return


async def get_products(
        session: aiohttp.ClientSession,
        product_name: str,
        sorting_type: str
) -> dict:
    result = dict()
    if sorting_type in ("new", "price", "rating"):
        params = {'text': product_name, 'from_global': 'true', 'sorting': sorting_type}
    else:
        params = {'text': product_name, 'from_global': 'true'}
    print(sorting_type, params)
    page_data = await get_page_data(session, params)
    if client_state := page_data.find(class_="client-state"):
        grid_data = client_state.select_one('[id^="state-tileGridDesktop-"]')
        filter_data = client_state.select_one('[id^="state-filtersDesktop-"]')
        if grid_data and grid_data.get('data-state'):
            products = json.loads(grid_data.get('data-state')).get('items', list())
            result["products"] = products
            result["product_top"] = products[:1]
        if filter_data and filter_data.get('data-state'):
            filters_data = json.loads(filter_data.get('data-state'))
            result["filters"] = filters_data
    return result


async def get_page_data(
        session: aiohttp.ClientSession,
        params: dict[str, str]
) -> BeautifulSoup:
    page_data = await parse_search(session, params)
    if search_match := re.search(pattern=r'location\.replace\(\"(.*?)\"\)', string=page_data):
        search_url = json.loads(f'"{search_match.group(1)}"')
        page_data = await parse_product(session, search_url)
    return BeautifulSoup(page_data, 'html.parser')


async def get_product_name(
        session: aiohttp.ClientSession,
        product_url: str
) -> tuple[Optional[str], int]:
    prefix, product_name, sku_id = None, None, int()
    pattern = r'https://(?:www.)?ozon.ru(/(?:product|t)/[a-zA-Z\d-]+/?)'
    if match := re.search(pattern=pattern, string=product_url):
        product_url, main_url = match.group(1), 'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url='
        parse_url = f'{main_url}{product_url}?layout_container=pdpPage2column&layout_page_index=1'
        product_data = await parse_product(session, parse_url)
        product_data = json.loads(product_data)
        for name, value in product_data.get('widgetStates', dict()).items():
            if name.startswith('breadCrumbs-') and value != '{}':
                data = json.loads(value)
                *_, last_item = data.get('breadcrumbs', list())
                prefix = last_item.get('text', '')
            elif name.startswith('webStickyProducts-') and value != '{}':
                data = json.loads(value)
                sku_id = int(data.get('sku', '0'))
                product_name = data.get('name', '')
        else:
            return f'{prefix} {product_name}', sku_id
    else:
        return None, 0


@log_decorators.save_request_info
@retry_decorators.retry_request(default_value='{}', raise_error=True, attempts=3, delay=5)
async def parse_details(
        session: aiohttp.ClientSession,
        sku: str
) -> tuple[str, int, str]:
    async with session.get(
            url=(
                    f'https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url='
                    f'/product/{sku}/?layout_container=pdpPage2column&layout_page_index=2'
            ),
            timeout=aiohttp.ClientTimeout(25)
    ) as response:
        return str(response.url), response.status, await response.text()


@log_decorators.save_request_info
@retry_decorators.retry_request(default_value='', raise_error=True, attempts=3, delay=5)
async def parse_search(
        session: aiohttp.ClientSession,
        params: dict
) -> tuple[str, int, str]:
    async with session.get(
            url=f'https://www.ozon.ru/search/',
            params=params,
            timeout=aiohttp.ClientTimeout(total=25)
    ) as response:
        return str(response.url), response.status, await response.text()


@log_decorators.save_request_info
@retry_decorators.retry_request(default_value='{}', raise_error=True, attempts=3, delay=5)
async def parse_product(
        session: aiohttp.ClientSession,
        url: str
) -> tuple[str, int, str]:
    async with session.get(
            url=url,
            timeout=aiohttp.ClientTimeout(total=25)
    ) as response:
        return str(response.url), response.status, await response.text()


async def get_headers() -> dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "cookie": "__Secure-ab-group=10; xcid=b4a90f8e1a173da2fb0dd768c7cfa188; __Secure-ext_xcid=b4a90f8e1a173da2fb0dd768c7cfa188; is_adult_confirmed=; is_alco_adult_confirmed=; __Secure-user-id=67543454; bacntid=2437214; sc_company_id=60617; __Secure-ETC=7d6318d259a11b2855e230b87265ef86; abt_data=7.dzHCEcb_ao4UtvRuofC_3jb8bO38AjglWSc7fcasi3AJnCJEaUaGPY0lY7uosQyHMloFaNjXQw-LpQ9DtMf92ZOkAIzpG85vMOmjDZkH5WfOWn2hHtJUo1l1zaP85RTNYyFhasfPFJBQdQpiTjndN73hpHHkggdvFpQ6Ev3LXFwYLJkj0Oi102Emx-5HR_x_NjFIAarj38rI59m6o06I2FwH8RoFYF62FiSlcP-fFWHVghY73CZYmqbHkT7ScY68zYUQqtwd0A0kujDil5mDKU5AmMmyaBGdxnF8mEPXGwydUpqQieGvwM2C2bRRewdxhKARf0hSCOydSQVGtfjwIzbYgxaEyVAteRPGEBFBl3NIzkEzqSLdJf3U0U-3a00wBMFjVwcm1BUMSDxGaDykgF03CO1M_x-wm4fdL7uHjlBk5Uk3ChKXPRVYeabPWuGoeG5VD5kJx06Tb0gvCciSTYwsFcJWPdgZqswiSuwBof15uRPqygM6W59VZ53ic_A4wPa42ColskE6IqfT-AUuZOa6TPwPcX24eue2aKuRCb9zpWG5QR1cGnMOks2qAHfO0eO-8ZpAsIS6FV8iQliihjqGdPi6hJWCw5lhnnYWZY4ZAXwNpudUFR8dTBlJVHYFRY89jctxR6ltn90pmXd1bc1Cg-lm; rfuid=LTE5NTAyNjU0NzAsMTI0LjA0MzQ3NTI3NTE2MDc0LDE5MDczMzM5MzQsLTEsODM5NTE1NDY3LFczc2libUZ0WlNJNklsQkVSaUJXYVdWM1pYSWlMQ0prWlhOamNtbHdkR2x2YmlJNklsQnZjblJoWW14bElFUnZZM1Z0Wlc1MElFWnZjbTFoZENJc0ltMXBiV1ZVZVhCbGN5STZXM3NpZEhsd1pTSTZJbUZ3Y0d4cFkyRjBhVzl1TDNCa1ppSXNJbk4xWm1acGVHVnpJam9pY0dSbUluMHNleUowZVhCbElqb2lkR1Y0ZEM5d1pHWWlMQ0p6ZFdabWFYaGxjeUk2SW5Ca1ppSjlYWDBzZXlKdVlXMWxJam9pUTJoeWIyMWxJRkJFUmlCV2FXVjNaWElpTENKa1pYTmpjbWx3ZEdsdmJpSTZJbEJ2Y25SaFlteGxJRVJ2WTNWdFpXNTBJRVp2Y20xaGRDSXNJbTFwYldWVWVYQmxjeUk2VzNzaWRIbHdaU0k2SW1Gd2NHeHBZMkYwYVc5dUwzQmtaaUlzSW5OMVptWnBlR1Z6SWpvaWNHUm1JbjBzZXlKMGVYQmxJam9pZEdWNGRDOXdaR1lpTENKemRXWm1hWGhsY3lJNkluQmtaaUo5WFgwc2V5SnVZVzFsSWpvaVEyaHliMjFwZFcwZ1VFUkdJRlpwWlhkbGNpSXNJbVJsYzJOeWFYQjBhVzl1SWpvaVVHOXlkR0ZpYkdVZ1JHOWpkVzFsYm5RZ1JtOXliV0YwSWl3aWJXbHRaVlI1Y0dWeklqcGJleUowZVhCbElqb2lZWEJ3YkdsallYUnBiMjR2Y0dSbUlpd2ljM1ZtWm1sNFpYTWlPaUp3WkdZaWZTeDdJblI1Y0dVaU9pSjBaWGgwTDNCa1ppSXNJbk4xWm1acGVHVnpJam9pY0dSbUluMWRmU3g3SW01aGJXVWlPaUpOYVdOeWIzTnZablFnUldSblpTQlFSRVlnVm1sbGQyVnlJaXdpWkdWelkzSnBjSFJwYjI0aU9pSlFiM0owWVdKc1pTQkViMk4xYldWdWRDQkdiM0p0WVhRaUxDSnRhVzFsVkhsd1pYTWlPbHQ3SW5SNWNHVWlPaUpoY0hCc2FXTmhkR2x2Ymk5d1pHWWlMQ0p6ZFdabWFYaGxjeUk2SW5Ca1ppSjlMSHNpZEhsd1pTSTZJblJsZUhRdmNHUm1JaXdpYzNWbVptbDRaWE1pT2lKd1pHWWlmVjE5TEhzaWJtRnRaU0k2SWxkbFlrdHBkQ0JpZFdsc2RDMXBiaUJRUkVZaUxDSmtaWE5qY21sd2RHbHZiaUk2SWxCdmNuUmhZbXhsSUVSdlkzVnRaVzUwSUVadmNtMWhkQ0lzSW0xcGJXVlVlWEJsY3lJNlczc2lkSGx3WlNJNkltRndjR3hwWTJGMGFXOXVMM0JrWmlJc0luTjFabVpwZUdWeklqb2ljR1JtSW4wc2V5SjBlWEJsSWpvaWRHVjRkQzl3WkdZaUxDSnpkV1ptYVhobGN5STZJbkJrWmlKOVhYMWQsV3lKeWRTMVNWU0pkLDAsMSwwLDI0LDIzNzQxNTkzMCw4LDIyNzEyNjUyMCwwLDEsMCwtNDkxMjc1NTIzLFIyOXZaMnhsSUVsdVl5NGdUbVYwYzJOaGNHVWdSMlZqYTI4Z1YybHVNeklnTlM0d0lDaFhhVzVrYjNkeklFNVVJREV3TGpBN0lGZHBialkwT3lCNE5qUXBJRUZ3Y0d4bFYyVmlTMmwwTHpVek55NHpOaUFvUzBoVVRVd3NJR3hwYTJVZ1IyVmphMjhwSUVOb2NtOXRaUzh4TXpndU1DNHdMakFnVTJGbVlYSnBMelV6Tnk0ek5pQXlNREF6TURFd055Qk5iM3BwYkd4aCxleUpqYUhKdmJXVWlPbnNpWVhCd0lqcDdJbWx6U1c1emRHRnNiR1ZrSWpwbVlXeHpaU3dpU1c1emRHRnNiRk4wWVhSbElqcDdJa1JKVTBGQ1RFVkVJam9pWkdsellXSnNaV1FpTENKSlRsTlVRVXhNUlVRaU9pSnBibk4wWVd4c1pXUWlMQ0pPVDFSZlNVNVRWRUZNVEVWRUlqb2libTkwWDJsdWMzUmhiR3hsWkNKOUxDSlNkVzV1YVc1blUzUmhkR1VpT25zaVEwRk9UazlVWDFKVlRpSTZJbU5oYm01dmRGOXlkVzRpTENKU1JVRkVXVjlVVDE5U1ZVNGlPaUp5WldGa2VWOTBiMTl5ZFc0aUxDSlNWVTVPU1U1SElqb2ljblZ1Ym1sdVp5SjlmWDE5LDY1LC0xNzcxMDM5NDI3LDEsMSwtMSwxNjk5OTU0ODg3LDE2OTk5NTQ4ODcsMTkxNzUyMTQxMywxNg==; ADDRESSBOOKBAR_WEB_CLARIFICATION=1755081894; is_cookies_accepted=1; __Secure-access-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.10.ATSaRVw7sRMvRdbJnfqGxjbXpoUZw9gz3jNy_QKvXEmZEFn3I4GAAZadtgylfaMmQWVRctaZ_YbZrYhhxsu9bNX7a1_w4dQCbpw1SJEAWG2aGvI8bLduV6pRUXGmc_y2xw.20210516122836.20250813132147.jnsuiAb8-o0v-ZxNqqGkmPQNqOAbC-NOvyKYSzt9Wx4.19eb67ee25f84bc28; __Secure-refresh-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.10.ATSaRVw7sRMvRdbJnfqGxjbXpoUZw9gz3jNy_QKvXEmZEFn3I4GAAZadtgylfaMmQWVRctaZ_YbZrYhhxsu9bNX7a1_w4dQCbpw1SJEAWG2aGvI8bLduV6pRUXGmc_y2xw.20210516122836.20250813132147.qgCwK5ZcSmHsRvxCrouSeW-xH6RRvqdTsaKA2EUiM7U.1b7481c5b0aeb1bb4",
        "priority": "u=0, i",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
