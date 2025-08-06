import re
import aiohttp
import uuid
import json

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
        query = select(UrlProductsOrm).filter_by(unique_id=unique_id)
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
        "update_time": datetime.now()
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
        product_name: str
) -> tuple[bool, uuid.UUID | None]:
    async with async_session_maker() as db_session:
        query = select(SearchMatchOrm)
        matches = await db_session.execute(query)
        matches = {
            match.concat_name: {
                'unique_id': match.unique_id,
                'update_time': match.update_time
            }
            for match in matches.scalars().fetchall()
        }

    if product_name in matches:
        unique_id = matches[product_name]['unique_id']
        update_time = matches[product_name]['update_time']
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
        'https://ozon.by' + product.get('action', dict()).get('link')
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
                        result['description'] = description.get('richAnnotation')
                    else:
                        result['description'] = 'Rich-Content'

    for section in products.get('filters', dict()).get('sections', list()):
        for filter_ in section.get('filters', list()):
            if filter_.get('key') == 'currency_price':
                min_value = float(filter_.get('rangeFilter', dict()).get('minValue', '0'))
                max_value = float(filter_.get('rangeFilter', dict()).get('maxValue', '1'))
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
                    characteristic_name = characteristic.get('name')
                    for value in characteristic.get('values', list()):
                        result[characteristic_name].append(value.get('text'))
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
    """
    Ссылка на файл со списком всех позиций, можно google sheet
    Ссылки на топ 5 самых дешевых
    Ссылка на топ 5 самых популярных
    Ссылки на топ 5 самых рейтинговых (и с наибольшим количеством отзывов)
    1 картинку самого популярного
    1 короткое описание самого популярного в формате цитаты в сообщении
    1 информацию о товаре до 5-7 атрибутов
    Средняя цена Avg Price в диапазоне от Min Price до Max Price
    """
    result = dict()
    if sorting_type in ("price", "rating"):
        params = {'text': product_name, 'from_global': 'true', 'sorting': sorting_type}
    else:
        params = {'text': product_name, 'from_global': 'true'}
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
    result, sku_id = str(), int()
    if match := re.search(pattern=r'https://ozon.by(/product/[a-z-\d]+?/)', string=product_url):
        product_url, main_url = match.group(1), 'https://www.ozon.by/api/entrypoint-api.bx/page/json/v2?url='
        parse_url = f'{main_url}{product_url}?layout_container=pdpPage2column&layout_page_index=1'
        product_data = await parse_product(session, parse_url)
        product_data = json.loads(product_data)
        for name, value in product_data.get('widgetStates', dict()).items():
            if name.startswith('breadCrumbs-') and value != '{}':
                data = json.loads(value)
                *_, category, brand = data.get('breadcrumbs', list())
                result += f"{category.get('text')} {brand.get('text')} "
            elif name.startswith('webStickyProducts-') and value != '{}':
                data = json.loads(value)
                sku_id = int(data.get('sku', '0'))
                result += f"{data.get('name')} "
        else:
            return result, sku_id
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
                    f'https://www.ozon.by/api/entrypoint-api.bx/page/json/v2?url='
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
            url=f'https://www.ozon.by/search/',
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
        "cookie": "__Secure-ab-group=45; __Secure-ext_xcid=d6e7218ee0d602264849ff815dcb577d; cookie_settings=eyJhbGciOiJIUzI1NiIsIm96b25pZCI6Im5vdHNlbnNpdGl2ZSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTIzMjQwODIsImlzcyI6Im96b25pZCIsInN1YiI6InRva2VuX2tpbmRfZ2Rwcl9jb29raWVzIiwibWFya2V0aW5nIjpmYWxzZSwic3RhdGlzdGljIjpmYWxzZSwicHJlZmVyZW5jZXMiOmZhbHNlfQ.OFWfWqzKJi7s6qSysDxQMetrasRUPaPWPdtMutpV3b0; __Secure-access-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.45.ASsDIVsCmDiD1i3YppojNk2TQ-0H7Slg0DYYylfjeezmB914n4ZIpVn26LTQZLirNssuKFT4L_Pq441r7CujwgJnvCA9ts-q8zdFr4oLcFSJWaQX23pEOYo7jXrd8z3rwg.20210516122836.20250804204903.ciuleuj1-GbRcmc3_9JPMBezbthaY-9YB-1YSh4Hzks.1416e8a8d3ecc93a5; __Secure-refresh-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.45.ASsDIVsCmDiD1i3YppojNk2TQ-0H7Slg0DYYylfjeezmB914n4ZIpVn26LTQZLirNssuKFT4L_Pq441r7CujwgJnvCA9ts-q8zdFr4oLcFSJWaQX23pEOYo7jXrd8z3rwg.20210516122836.20250804204903.FNlRcR7vG61StXgb6h0QVsdyEuzvoT3cotf4WQ32Oes.16ad44035a106bde8; __Secure-user-id=67543454; xcid=12b1e82fdd1c84f637267c1b48ca7ad4; abt_data=7.gi-r-RFn97WDddi5Tq-qQcNzKzN7qK0Ytc7g3rW_h_rEIq3xpDGgT-ZJ7WYPboXYwwB9jAjD4rQteYKcGZcxNtGm4L8wF03CGPB9XP0OeJLiv--ZJr2ZsZBmJ4WXDbExgqmCPnH6If4E2B_TUztYQXemisVnIn-3s0hzyeb_xUU29yQ7cvCOC7bvgcpQakgzPhM08UGZ5gxf79wkx0Lm_0555A69aV9OwSp0iS6cOmWecc7bRLuCNbVQZp1WfPoKDawxfZ4yOkTA2NLlZ_LTKoYyCrsAOf8neK3l4zjY0yvqspLukgRFbg9ZTgUP9QsZt5OVqOD2ImAV7Jjvp9aiRjfD6BjXTle5WCwVgJCB5jTutWLodEYoAVpcZQrqoONQN83pvbvgKHtlNRcqOYEFclUpElddBimRregJAT5ErjXcSoN75ShdgmeYOvIGOIjQCfRHWckM90NV5sORn5qg9HLhVShu87mpH_jbVo5kd9nHz0rMr_ryjLoYvM2Mr4KJrKcF_v9U8iq52V-w3QOiwlow9RK1GybvcQcLZl8oJpqoTpA-qnJlEIcest3Tr6gAgE8TW9iR3roRzKM7ae2u5CCUJuRkvqcVok1Ft7KcWJ4duVcs97a-Ii3A4wuJie4zJDh4fjy1vwyHn1xpQDy75Ds; __Secure-ETC=cde43bfc9fa61995bf2ec3dd50d3bae1",
        "priority": "u=0, i",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
