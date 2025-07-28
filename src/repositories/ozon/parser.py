import re
import asyncio
import aiohttp
import json

from collections import defaultdict
from typing import Optional, Any
from bs4 import BeautifulSoup

from src.utils import retry_decorators, log_decorators


async def get_product_data(
        product_url: str
) -> dict:
    headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        if product_name := await get_product_name(session, product_url):
            products = await get_products(session, product_name)
            return await format_products(session, products)
        else:
            return dict()


async def format_products(
        session: aiohttp.ClientSession,
        products: dict[str, Any]
) -> dict:
    result = dict()
    for key in ('price', 'score', 'rating', 'description', 'avg_price'):
        match key:
            case 'price' | 'score' | 'rating':
                result[f'"products_{key}'] = [
                    'https://ozon.by' + product.get('action', dict()).get('link')
                    for product in products.get('price', list())[:5]
                ]
            case 'description':
                for product in products.get('product_top', list()):
                    result['main_image'] = await get_main_image(product)
                    details = await parse_details(session, product.get('sku'))
                    for name, value in json.loads(details).get('widgetStates', dict()).items():
                        if name.startswith('webCharacteristics-') and value != '{}':
                            result['characteristics'] = await get_characteristics(json.loads(value))
            case 'avg_price':
                for section in products.get('filters', dict()).get('sections', list()):
                    for filter_ in section.get('filters', list()):
                        if filter_.get('key') == 'currency_price':
                            min_value = float(filter_.get('rangeFilter', dict()).get('minValue', '0'))
                            max_value = float(filter_.get('rangeFilter', dict()).get('maxValue', '1'))
                            result['currency_price'] = {
                                'min_price': min_value,
                                'max_price': max_value,
                                'avg_price': min_value + max_value / 2
                            }
    else:
        return result


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
        product_name: str
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
    for sorting_type in ('price', 'score', 'rating'):
        if sorting_type == "score":
            params = {'text': product_name, 'from_global': 'true'}
        else:
            params = {'text': product_name, 'from_global': 'true', 'sorting': sorting_type}
        page_data = await parse_search(session, params)
        page_data = BeautifulSoup(page_data, 'html.parser')
        await asyncio.sleep(0.5)
        if client_state := page_data.find(class_="client-state"):
            grid_data = client_state.select_one('[id^="state-tileGridDesktop-"]')
            filter_data = client_state.select_one('[id^="state-filtersDesktop-"]')
            if grid_data and grid_data.get('data-state'):
                products = json.loads(grid_data.get('data-state')).get('items', list())
                result[sorting_type] = products
                if sorting_type == "score":
                    result["product_top"] = products[:1]
            if sorting_type == 'score' and filter_data and filter_data.get('data-state'):
                filters_data = json.loads(filter_data.get('data-state'))
                result["filters"] = filters_data
    else:
        return result


async def get_product_name(
        session: aiohttp.ClientSession,
        product_url: str
) -> Optional[str]:
    result = str()
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
                result += f"{data.get('name')} "
        else:
            return result
    else:
        return


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
        'accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,'
            '*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
        ),
        'accept-encoding': 'gzip, deflate, br, zstd',
        'accept-language': 'ru-RU,ru;q=0.9',
        'cookie': '__Secure-ab-group=45; __Secure-ext_xcid=d6e7218ee0d602264849ff815dcb577d; cookie_settings=eyJhbGciOiJIUzI1NiIsIm96b25pZCI6Im5vdHNlbnNpdGl2ZSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTIzMjQwODIsImlzcyI6Im96b25pZCIsInN1YiI6InRva2VuX2tpbmRfZ2Rwcl9jb29raWVzIiwibWFya2V0aW5nIjpmYWxzZSwic3RhdGlzdGljIjpmYWxzZSwicHJlZmVyZW5jZXMiOmZhbHNlfQ.OFWfWqzKJi7s6qSysDxQMetrasRUPaPWPdtMutpV3b0; __Secure-user-id=67543454; xcid=cb2282547bbe3df04901fde836283e76; __Secure-access-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.45.AU9aeK1dHLRQEkuKqZY2w7j_fZknkGqPxmYy3_7RTkZ4Imko9Ov3yWd4Xu0kozeb8u6uKZL5i2RF3GPcMeFzJTeCk7ulfuQ5sxAmi040njKv_OVxs5Aqk2aEjr6_3M9nWw.20210516122836.20250724183909.xHKtqvDo3J2i1HF4FZbiXiz8tGowgu5En6M4LgPOgUs.1a8e380ebcf7967e9; __Secure-refresh-token=8.67543454.jRff97XaTX-yNwpp6rD-jw.45.AU9aeK1dHLRQEkuKqZY2w7j_fZknkGqPxmYy3_7RTkZ4Imko9Ov3yWd4Xu0kozeb8u6uKZL5i2RF3GPcMeFzJTeCk7ulfuQ5sxAmi040njKv_OVxs5Aqk2aEjr6_3M9nWw.20210516122836.20250724183909.o3ZdT5I3bu9uLRob511AfKFBlULIxs485pJiVKNrFK8.1d9e211d36764902b; __Secure-ETC=3a077323b33bcc195bb1a562218de2d3; abt_data=7.2HCYoWZ8911Q7b5ozdzvFZkEbEvEdNXYkYnXU71b6EJBGumQk51yTja6HzYGlYq7H9b-7PSn19MyKamURfMzfW4Nc4pWVE6DO40cMXtOzoxY10TlqeMZF-RA_oKBzg0wnD6Oa4HW3e9d2XDYRz7c7geYtd1vCcVVQ0BbhHqQ6AMmkijBmS4T6ocIoi19n8-1L4_xu7EIl_MfktceH_ojVaFWP4o3DONENoXNii6c_dO7DPGwSjF6kx3Nu3qj6Br3Y9bTjsHkDUikf_s-0RBEjkWwAjfEyDisd7ALzetg0G3uPqfVhZ627Bx8n3rsDpUvtYoj6gpPshYn8BUG0D-kmCoDoa_Qkl_j6D31a5wT4kuSJPIRDlS-iYBvHfdodIuLhGylRLasX6MHFZ7VngaKyV9NoHA0oB8hxbflKYnVlcoqBWrpEbhBhlmtTIikLiwFCUER64PQf2UIJLx2sVOoZckfJDbM01-SyOhZZVnMVOPy3Hm2xlXdCrUFHUWM5L4bDd99tu3SN4O4e1B9SAtoBiu767ELw-idro_HNV08MCf4wEKQDm-yiszAnfro8JurKzW3LqSsRxlFvyfmjA9ncjjGVZNHOY-RdqjEvzVL6dkZ1qNBmODG_JQGkCBIfSf3Vdm2P2DSK_llvhMiungRGBAA',
        'priority': 'u=0, i',
        'upgrade-insecure-requests': '1',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
        )
    }


if __name__ == "__main__":
    # from urllib.parse import unquote
    # print(unquote('https://ozon.by/api/entrypoint-api.bx/page/json/v2?url=%2Fproduct%2Fmarker-stroitelnyy-tonkiy-razmetochnyy-s-dlinnym-nakonechnikom-5-sht-chernyy-krasnyy-zelenyy-1469493008%2F%3Fat%3DMZtvp1o8rSQ9xvwxfJ9K60oFJvVZxpCYK6GEJTMxW9QA%26layout_container%3DpdpPage2column%26layout_page_index%3D2%26sh%3DG8YCmrOZPg%26start_page_id%3D86a4b0c49cc13425259962266a308b88'))
    asyncio.run(get_product_data(
        "https://ozon.by/product/marker-stroitelnyy-tonkiy-razmetochnyy-s-dlinnym-nakonechnikom-5-sht-chernyy-krasnyy-zelenyy-1469493008/?at=MZtvp1o8rSQ9xvwxfJ9K60oFJvVZxpCYK6GEJTMxW9QA"
    ))
