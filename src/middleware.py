from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from typing import Callable

from src.config import settings


class SecretKeyCheck(BaseHTTPMiddleware):
    async def dispatch(
            self,
            request: Request,
            next_call: Callable
    ) -> JSONResponse:
        request_key = request.headers.get("X-Secret-Key")
        if request_key != settings.SECRET_KEY:
            return JSONResponse(
                status_code=403,
                content={"detail": "Access denied: invalid or missing secret key"}
            )
        else:
            return await next_call(request)
