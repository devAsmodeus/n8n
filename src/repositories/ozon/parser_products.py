import re
import aiohttp
import json

from collections import defaultdict
from typing import Optional, Any, Callable
from bs4 import BeautifulSoup

from src.repositories.ozon.requests import (
    parse_product,
    parse_search,
    parse_details
)


async def get_product_name(
        product_url: str,
) -> tuple[str, int]:
    headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_name, sku_id = await format_product_name(session, product_url)
        if product_name:
            return product_name, sku_id
        else:
            return "Наименование не распознано", 0


async def format_product_name(
        session: aiohttp.ClientSession,
        product_url: str,
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
            if str(prefix).lower() in str(product_name).lower():
                return product_name, sku_id
            else:
                return f'{prefix} {product_name}', sku_id
    else:
        return None, 0


async def get_product_data(
        product_name: str,
        sorting_type: str,
) -> dict[str, Any]:
    # exists_flag, unique_id = await check_exists(product_name, sorting_type)
    exists_flag, unique_id = True, None
    if exists_flag:
        headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            if products := await get_products(session, product_name, sorting_type):
                products = await format_products(session, products)
                # await upload_products(product_url, product_name, sku_id, products)
                return products
            else:
                return dict()
    else:
        db_info = await get_database_info(unique_id, sorting_type)
        return db_info


async def get_products(
        session: aiohttp.ClientSession,
        product_name: str,
        sorting_type: str,
) -> dict:
    result = dict()
    if sorting_type in ("new", "price", "rating"):
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
        params: dict[str, str],
) -> BeautifulSoup:
    page_data = await parse_search(session, params)
    if search_match := re.search(pattern=r'location\.replace\(\"(.*?)\"\)', string=page_data):
        search_url = json.loads(f'"{search_match.group(1)}"')
        page_data = await parse_product(session, search_url)
    return BeautifulSoup(page_data, 'html.parser')


async def format_products(
        session: aiohttp.ClientSession,
        products: dict[str, Any],
) -> dict:
    products_data = list() # Ссылки на товары, цены, рейтинг и количество отзывов
    currency_prices = dict() # Схема с минимальной и максимальной ценой (средняя цена)
    product_name = None # Наименование самого популярного товара
    product_image = None # Главное и первое изображение самого популярного товара
    description = None # Описание товара с Rich-контентом самого популярного товара
    characteristics = None # Характеристики самого популярного товара
    for product_number, product in enumerate(products.get('products', list()), start=1):
        products_data.append(await get_product_rating(product))
        if product_number == 1:
            product_top_result_data = await get_product_top_data(session, products)
            product_name, product_image, description, characteristics = product_top_result_data
    else:
        currency_prices.update(await get_currency_prices(products))
        return dict(
            products_data=products_data,
            currency_prices=currency_prices,
            product_name=product_name,
            product_image=product_image,
            description=description,
            characteristics=characteristics,
        )


async def get_product_rating(
        product: dict[str, Any],
) -> dict[str, Any]:
    product_url = 'https://www.ozon.ru' + product.get('action', dict()).get('link')
    result = dict()
    for state in product.get('mainState', list()):
        for key, value in state.items():
            if key == 'labelList':
                for item in value.get('items', list()):
                    item_name = item.get('testInfo', dict()).get('automatizationId')
                    result[item_name] = item.get('title')
            elif key == 'textAtom':
                item_name = value.get('testInfo', dict()).get('automatizationId')
                result[item_name] = value.get('text')
            elif key == 'priceV2':
                for price in value.get('price', list()):
                    item_name = price.get('textStyle')
                    result[item_name] = price.get('text')
    else:
        return dict(
            url=product_url,
            name=str(result.get('tile-name')).strip(),
            price=await format_str_to_int(result.get('PRICE'), int),
            rating=await format_str_to_int(result.get('tile-list-rating'), float),
            reviews=await format_str_to_int(result.get('tile-list-comments'), int),
        )


async def format_str_to_int(
        value: str,
        format_type: Callable,
        default_value: str = 'Нет'
) -> float | int | None | str:
    if value:
        if format_type is int:
            value = ''.join(char for char in str(value) if char.isdigit())
        else:
            value = ''.join(char for char in str(value) if char.isdigit() or char == '.')

        return format_type(value)
    else:
        return default_value


async def get_product_top_data(
        session: aiohttp.ClientSession,
        products: dict[str, Any],
) -> tuple | tuple[None, str | None, str | Any, dict[Any, Any]]:
    product_name = None
    product_image = None
    description = str()
    characteristics = dict()
    for product in products.get('product_top', list()):
        product_image = await get_main_image(product)
        product_data_ = await get_product_rating(product)
        product_name = product_data_.get('name')
        details = await parse_details(session, product.get('sku'))
        for name, value in json.loads(details).get('widgetStates', dict()).items():
            if name.startswith('webCharacteristics-') and value != '{}':
                characteristics.update(await get_characteristics(json.loads(value)))
            if name.startswith('webDescription-') and value != '{}':
                if 'richAnnotationType' in (rich := json.loads(value)):
                    if rich.get('richAnnotationType') == 'HTML':
                        if rich_text := rich.get('richAnnotation'):
                            description += rich_text + '\n'
                    else:
                        for row in rich.get('richAnnotationJson', dict()).get('content', list()):
                            for block in row.get('blocks', list()):
                                for text in block.get('text', dict()).get('content', list()):
                                    description += text + '\n'
                if 'characteristics' in (rich := json.loads(value)):
                    for row in rich.get('characteristics', list()):
                        key, value = row.get('title'), row.get('content')
                        description += f'{key}: {value}\n'
        else:
            description = description if description.strip() else 'Описание не найдено'
            description = re.sub(pattern=r'</?[a-z/]+>', repl='', string=description)

    return (
        product_name, product_image, description, characteristics
    )


async def get_characteristics(
        data: dict[str, Any]
) -> dict:
    result = defaultdict(list)
    for part_data in data.get('characteristics', list()):
        for _, characteristics in part_data.items():
            if isinstance(characteristics, list):
                for characteristic in characteristics:
                    if characteristic_name := characteristic.get('name'):
                        for value in characteristic.get('values', list()):
                            if characteristic_values := value.get('text'):
                                result[characteristic_name].append(characteristic_values)
    else:
        return result


async def get_main_image(
        product: dict[str, Any]
) -> Optional[str]:
    for item in product.get('tileImage', dict()).get('items', list()):
        return item.get('image', dict()).get('link')
    else:
        return None


async def get_currency_prices(
        products: dict[str, Any],
) -> dict[str, Any]:
    result = dict()
    for section in products.get('filters', dict()).get('sections', list()):
        for filter_ in section.get('filters', list()):
            if filter_.get('key') == 'currency_price':
                filter_data = filter_.get('multipleRangesFilter', dict()).get('rangeFilter', dict())
                result['min_price'] = float(filter_data.get('minValue', '0'))
                result['max_price'] = float(filter_data.get('maxValue', '0'))
                result['avg_price'] = round((result['min_price'] + result['max_price']) / 2, 2)
    else:
        return result


async def get_headers() -> dict[str, str]:
    return {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "cookie": "__Secure-ab-group=10; xcid=b4a90f8e1a173da2fb0dd768c7cfa188; __Secure-ext_xcid=b4a90f8e1a173da2fb0dd768c7cfa188; is_adult_confirmed=; is_alco_adult_confirmed=; bacntid=2437214; is_cookies_accepted=1; sc_company_id=967555; TSDK_trackerSessionId=26331e62-30df-4e50-e2ea; ADDRESSBOOKBAR_WEB_CLARIFICATION=1756802775; rfuid=LTE5NTAyNjU0NzAsMTI0LjA0MzQ3NTI3NTE2MDc0LDE1NzQ0Mjk2OTMsLTEsMTgwNDc3Njg3MSxXM3NpYm1GdFpTSTZJbEJFUmlCV2FXVjNaWElpTENKa1pYTmpjbWx3ZEdsdmJpSTZJbEJ2Y25SaFlteGxJRVJ2WTNWdFpXNTBJRVp2Y20xaGRDSXNJbTFwYldWVWVYQmxjeUk2VzNzaWRIbHdaU0k2SW1Gd2NHeHBZMkYwYVc5dUwzQmtaaUlzSW5OMVptWnBlR1Z6SWpvaWNHUm1JbjBzZXlKMGVYQmxJam9pZEdWNGRDOXdaR1lpTENKemRXWm1hWGhsY3lJNkluQmtaaUo5WFgwc2V5SnVZVzFsSWpvaVEyaHliMjFsSUZCRVJpQldhV1YzWlhJaUxDSmtaWE5qY21sd2RHbHZiaUk2SWxCdmNuUmhZbXhsSUVSdlkzVnRaVzUwSUVadmNtMWhkQ0lzSW0xcGJXVlVlWEJsY3lJNlczc2lkSGx3WlNJNkltRndjR3hwWTJGMGFXOXVMM0JrWmlJc0luTjFabVpwZUdWeklqb2ljR1JtSW4wc2V5SjBlWEJsSWpvaWRHVjRkQzl3WkdZaUxDSnpkV1ptYVhobGN5STZJbkJrWmlKOVhYMHNleUp1WVcxbElqb2lRMmh5YjIxcGRXMGdVRVJHSUZacFpYZGxjaUlzSW1SbGMyTnlhWEIwYVc5dUlqb2lVRzl5ZEdGaWJHVWdSRzlqZFcxbGJuUWdSbTl5YldGMElpd2liV2x0WlZSNWNHVnpJanBiZXlKMGVYQmxJam9pWVhCd2JHbGpZWFJwYjI0dmNHUm1JaXdpYzNWbVptbDRaWE1pT2lKd1pHWWlmU3g3SW5SNWNHVWlPaUowWlhoMEwzQmtaaUlzSW5OMVptWnBlR1Z6SWpvaWNHUm1JbjFkZlN4N0ltNWhiV1VpT2lKTmFXTnliM052Wm5RZ1JXUm5aU0JRUkVZZ1ZtbGxkMlZ5SWl3aVpHVnpZM0pwY0hScGIyNGlPaUpRYjNKMFlXSnNaU0JFYjJOMWJXVnVkQ0JHYjNKdFlYUWlMQ0p0YVcxbFZIbHdaWE1pT2x0N0luUjVjR1VpT2lKaGNIQnNhV05oZEdsdmJpOXdaR1lpTENKemRXWm1hWGhsY3lJNkluQmtaaUo5TEhzaWRIbHdaU0k2SW5SbGVIUXZjR1JtSWl3aWMzVm1abWw0WlhNaU9pSndaR1lpZlYxOUxIc2libUZ0WlNJNklsZGxZa3RwZENCaWRXbHNkQzFwYmlCUVJFWWlMQ0prWlhOamNtbHdkR2x2YmlJNklsQnZjblJoWW14bElFUnZZM1Z0Wlc1MElFWnZjbTFoZENJc0ltMXBiV1ZVZVhCbGN5STZXM3NpZEhsd1pTSTZJbUZ3Y0d4cFkyRjBhVzl1TDNCa1ppSXNJbk4xWm1acGVHVnpJam9pY0dSbUluMHNleUowZVhCbElqb2lkR1Y0ZEM5d1pHWWlMQ0p6ZFdabWFYaGxjeUk2SW5Ca1ppSjlYWDFkLFd5SnlkUzFTVlNKZCwwLDEsMCwyNCwyMzc0MTU5MzAsOCwyMjcxMjY1MjAsMCwxLDAsLTQ5MTI3NTUyMyxSMjl2WjJ4bElFbHVZeTRnVG1WMGMyTmhjR1VnUjJWamEyOGdWMmx1TXpJZ05TNHdJQ2hYYVc1a2IzZHpJRTVVSURFd0xqQTdJRmRwYmpZME95QjROalFwSUVGd2NHeGxWMlZpUzJsMEx6VXpOeTR6TmlBb1MwaFVUVXdzSUd4cGEyVWdSMlZqYTI4cElFTm9jbTl0WlM4eE16a3VNQzR3TGpBZ1UyRm1ZWEpwTHpVek55NHpOaUF5TURBek1ERXdOeUJOYjNwcGJHeGgsZXlKamFISnZiV1VpT25zaVlYQndJanA3SW1selNXNXpkR0ZzYkdWa0lqcG1ZV3h6WlN3aVNXNXpkR0ZzYkZOMFlYUmxJanA3SWtSSlUwRkNURVZFSWpvaVpHbHpZV0pzWldRaUxDSkpUbE5VUVV4TVJVUWlPaUpwYm5OMFlXeHNaV1FpTENKT1QxUmZTVTVUVkVGTVRFVkVJam9pYm05MFgybHVjM1JoYkd4bFpDSjlMQ0pTZFc1dWFXNW5VM1JoZEdVaU9uc2lRMEZPVGs5VVgxSlZUaUk2SW1OaGJtNXZkRjl5ZFc0aUxDSlNSVUZFV1Y5VVQxOVNWVTRpT2lKeVpXRmtlVjkwYjE5eWRXNGlMQ0pTVlU1T1NVNUhJam9pY25WdWJtbHVaeUo5ZlgxOSw2NSwtMTc3MTAzOTQyNywxLDEsLTEsMTY5OTk1NDg4NywxNjk5OTU0ODg3LDE5MTc1MjE0MTMsMTY=; __Secure-ETC=b643ce838dd953f8d8a798d42e08eed8; __Secure-access-token=9.67543454.jRff97XaTX-yNwpp6rD-jw.10.AaQ69WWvTbJkaKbNHlYbKo68jWsAj5CwDMPhHgAjPcsXwviSde50mDNRhU8uTjefYwwwaQ4aGJ0OokwxLHZwbPx9Kwcnmj4M_U7MJskuVM-KtaJyBm2Tv4lxxNEe1dMGEA.20210516122836.20250904074859.6SyBkM2HX3J8R6rLvNnxiuBbwNNtxGVT1pH-Yz2hHag.1b4b8b306e0bd1370; __Secure-refresh-token=9.67543454.jRff97XaTX-yNwpp6rD-jw.10.AaQ69WWvTbJkaKbNHlYbKo68jWsAj5CwDMPhHgAjPcsXwviSde50mDNRhU8uTjefYwwwaQ4aGJ0OokwxLHZwbPx9Kwcnmj4M_U7MJskuVM-KtaJyBm2Tv4lxxNEe1dMGEA.20210516122836.20250904074859.1uJ3q2dG59Cgr45eoKPgapx3jwMnrsY3LkS4EdHQtqE.1f33f842c6e3ac415; __Secure-user-id=67543454; abt_data=7.4JP2pL61iY8X3tQYzIFqreTN5yNoxUAzGD3RFRbIL6PdA2Tim0VgEaIoEuKuDPykfyPvAo4PL92ua1rDDQo_j3npARw8uGNt7Bly3QdpUDKnZp3BrUwt725XEKiVLYNcPFmNLxjk7O8BIaGJBnkz-tLtGwsIkT_lUQkYq0GCDnzzsFW-2oA09X-zPiFGsyNUauGN9runpYZ7hS0m6aWYgoFWzvGMN--B6jFFLRZ2PlHDRNDD4ize0iUmZoxUQqxT2FxKQ-dVGInrUZU4nantsJS22rK3M2O-SoWmr0KJeV96EgwBdGfroZRPP2zGDC4hEdBjiUTHef7fiduaj2TvcKccCSxpM-AL3Vch-p7VCa0HSeEAuorOKi9cRBCGWIKDLzQ3gyE3KkurYFol7p6lUTRNm9wxqbn78XQIFEKkBagroLMz1jzrEiA-c7KZMXRusaQxW0PQUB_xXtGMRDY8s2W2VUV-zeQ6hVwQLVZXLFsQhYe-i0i-63K9cdr3lZJ8IExVsyyff74YXhTP8BuvEtxam7rcYTAbCDoUvG0nbXH35oC2OSFsMB5-hz4QYtc7WPE3H6jcUSYyhHcFz08twm5ijrtmmONZNofISh_Ld7IXwjNj--6Bmr-WmsaMddcYrJtDd92INKFvWSGTEA5Ev_isDA",
        "priority": "u=0, i",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
