from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.schemas import universal as scm_universal
from src.repositories.ozon import parser_products


router = APIRouter(
    prefix="/n8n/ozon",
    tags=["Методы для выгрузки данных Ozon"]
)


@router.get(path="/items/search")
async def get_items_search(
        product_url: str = Query(description="Ссылка на товар Озон", regex=r"https://ozon.by/product/.+"),
        sorting_type: str | None = Query(default="score", description="Тип сортировки товаров")
) -> JSONResponse:
    """
    Выполняет поиск и агрегацию данных по товару Ozon.

    Parameters
    ----------
    product_url : str
        Ссылка на карточку товара в домене `ozon.by`.
    sorting_type : str | None
        Тип сортировки выдачи: `score` (по умолчанию), `new`, `price`, `rating`.

    Returns
    -------
    JSONResponse
        Объект ответа с полями `error`, `message`, `results`.

    Notes
    -----
    - Внутри вызывает бизнес-логику парсинга/кэширования для получения агрегированных данных.
    - Формат `results` см. в документации (README.md).
    """
    response = scm_universal.ResultResponse(**{
        'error': False, 'message': None, 'results': None
    })
    try:
        response.results = await parser_products.get_product_data_depr(product_url, sorting_type)
    except Exception as cpm_exception:
        response.error = True
        response.message = repr(cpm_exception)
    finally:
        return JSONResponse(
            status_code=200,
            content=response.model_dump()
        )
