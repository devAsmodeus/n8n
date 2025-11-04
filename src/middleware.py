from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from typing import Callable

from src.config import settings


class SecretKeyCheck(BaseHTTPMiddleware):
    """
    Middleware для проверки заголовка `X-Secret-Key` в каждом запросе.

    Notes
    -----
    Чтобы активировать, раскомментируйте добавление middleware в `src/main.py`.
    """
    async def dispatch(
            self,
            request: Request,
            next_call: Callable
    ) -> JSONResponse:
        """
        Проверяет соответствие секрета из заголовка значению `settings.SECRET_KEY`.

        Parameters
        ----------
        request : Request
            Входящий HTTP-запрос.
        next_call : Callable
            Следующая функция-обработчик в цепочке.

        Returns
        -------
        JSONResponse
            403 при неверном/отсутствующем ключе, иначе — ответ следующего обработчика.
        """
        request_key = request.headers.get("X-Secret-Key")
        if request_key != settings.SECRET_KEY:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied: invalid or missing secret key"}
            )
        else:
            return await next_call(request)
