from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.schemas import universal as scm_universal


router = APIRouter(
    prefix="/n8n/ozon",
    tags=["Методы для выгрузки данных Ozon"]
)


@router.get(path="/items/search")
async def get_items_search(
        product_url: str = Query(description="Ссылка на товар Озон", regex=r"https://ozon.ru/product/.+")
) -> JSONResponse:
    response = scm_universal.ResultResponse(**{
        'error': False, 'message': None, 'results': None
    })
    try:
        response.results = dict(product_url=product_url)
    except Exception as cpm_exception:
        response.error = True
        response.message = repr(cpm_exception)
    finally:
        return JSONResponse(
            status_code=200,
            content=response.model_dump()
        )
