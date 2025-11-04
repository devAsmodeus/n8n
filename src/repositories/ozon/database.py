import uuid
import aiohttp

from typing import Any
from sqlalchemy import select, insert, delete
from datetime import datetime


from src.database import async_session_maker
from src.models.ozon import (
    SearchMatchOrm,
    UrlProductsOrm,
    ProductTopOrm,
    ProductCharacteristicsOrm
)

async def get_product_data_depr(
        product_url: str,
        sorting_type: str
) -> dict[str, Any]:
    """
    Устаревший интегрированный конвейер: парсинг -> сохранение -> возврат.

    Parameters
    ----------
    product_url : str
        Ссылка на карточку товара Ozon.
    sorting_type : str
        Тип сортировки поиска (score/new/price/rating).

    Returns
    -------
    dict[str, Any]
        Структурированный результат для ответа API.

    Notes
    -----
    - Проверяет наличие кэша в БД (`check_exists`).
    - При необходимости парсит и сохраняет (`upload_products`).
    - В противном случае читает из БД (`get_database_info`).
    """
    headers, connector = await get_headers(), aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        product_name, sku_id = await format_product_name(session, product_url)
        if product_name:
            exists_flag, unique_id = await check_exists(product_name, sorting_type)
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
    """
    Возвращает ранее сохраненные в БД результаты по уникальному ключу запроса.

    Parameters
    ----------
    unique_id : uuid.UUID
        Идентификатор выгрузки.
    sorting_type : str
        Тип сортировки, для которой нужно вернуть список URL и метаданные.

    Returns
    -------
    dict[str, Any]
        Объект с полями `details` (products, currency_price, main_image, description, characteristics).
    """
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
    """
    Сохраняет результаты парсинга в связанные таблицы PostgreSQL.

    Parameters
    ----------
    product_url : str
        Исходная ссылка на товар.
    product_name : str
        Имя (конкатенация) товара для поиска/кэширования.
    sku_id : int
        SKU товара.
    products : dict[str, Any]
        Агрегированные данные (`details`, `sorting_type`, и т.д.).

    Returns
    -------
    dict[str, Any]
        Изначально переданные данные `products` (для дальнейшего ответа).
    """
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
    """
    Проверяет наличие актуальной записи в БД для пары (product_name, sorting_type).

    Parameters
    ----------
    product_name : str
        Имя товара для поиска.
    sorting_type : str
        Тип сортировки выдачи.

    Returns
    -------
    tuple[bool, uuid.UUID | None]
        `(need_parse, unique_id)` — если данные актуальны (<=7 дней),
        возвращает `(False, unique_id)`; если требуется перепарсинг — `(True, None)`.
    """
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