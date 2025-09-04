import aiohttp

from src.utils import retry_decorators, log_decorators


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
