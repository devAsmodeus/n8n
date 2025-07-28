import asyncio

from functools import wraps
from typing import Callable, Optional, Any


class AuthenticationError(Exception):
    """Use for 401 and 403 status codes"""
    pass


class ManyRequestsError(Exception):
    """Use for 429 status code"""
    pass


class BadRequestError(Exception):
    """Use for 400 status code"""
    pass


class AnotherError(Exception):
    """Use for another errors"""
    pass


def retry_process(
        attempts: int = 2,
        delay: int = 15
) -> Callable:
    def decorator(function: Callable) -> Callable:
        @wraps(function)
        async def wrapper(*args, **kwargs) -> Optional[Any]:
            attempt, exception = attempts, None
            while attempt > 0:
                try:
                    result = await function(*args, **kwargs)
                    return result
                except Exception as exception_logger:
                    exception = exception_logger
                    attempt -= 1
                    await asyncio.sleep(delay)
            else:
                raise exception

        return wrapper

    return decorator


def retry_request(
        default_value: Any,
        raise_error: bool = False,
        return_bytes: bool = False,
        attempts: int = 5,
        delay: int | float = 15
) -> Callable:
    def decorator(function: Callable) -> Callable:
        @wraps(function)
        async def wrapper(*args, **kwargs) -> Any:
            attempt, exception = attempts, None
            url, status, text = None, None, None
            while attempt > 0:
                attempt -= 1
                try:
                    if response := await function(*args, **kwargs):
                        response: tuple[str, int, str | bytes] = response
                        url, status, text = response
                    else:
                        raise AnotherError('Ошибка другого формата')
                except Exception as exception_logger:
                    exception = exception_logger
                    await asyncio.sleep(delay)
                else:
                    if status in (200, 202, 204):
                        return url, status, text
                    elif status in (401, 403):
                        raise AuthenticationError('Авторизация устарела / Нет доступа')
                    else:
                        await asyncio.sleep(delay)
            else:
                if raise_error and exception:
                    raise exception
                elif raise_error and status == 429:
                    raise ManyRequestsError('Не получен ответ от сервера')
                elif raise_error:
                    raise AnotherError(text)
                elif all([url, status]):
                    return url, status, default_value
                else:
                    return 'Ошибка другого формата', '0', exception

        return wrapper

    return decorator
