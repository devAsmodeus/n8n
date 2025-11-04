import asyncio

from functools import wraps
from typing import Callable, Optional, Any


class AuthenticationError(Exception):
    """
    Исключение для кодов ответа 401/403 (проблемы аутентификации/доступа).
    """
    pass


class ManyRequestsError(Exception):
    """
    Исключение для кода ответа 429 (слишком много запросов).
    """
    pass


class BadRequestError(Exception):
    """
    Исключение для кода ответа 400 (некорректный запрос).
    """
    pass


class AnotherError(Exception):
    """
    Общее исключение для прочих ошибок.
    """
    pass


def retry_process(
        attempts: int = 2,
        delay: int = 15
) -> Callable:
    """
    Повторяет вызов асинхронной функции при возникновении исключений.

    Parameters
    ----------
    attempts : int
        Количество попыток (по умолчанию 2).
    delay : int
        Задержка между попытками в секундах.

    Returns
    -------
    Callable
        Обернутая функция, повторяющая выполнение при ошибках.
    """
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
    """
    Ретраи HTTP-запросов с обработкой статусов и возвратом значения по умолчанию.

    Parameters
    ----------
    default_value : Any
        Значение, возвращаемое при исчерпании попыток.
    raise_error : bool
        Если True — возбуждать исключение при неуспехе.
    return_bytes : bool
        Зарезервировано для режимов, где требуется вернуть bytes.
    attempts : int
        Кол-во попыток (по умолчанию 5).
    delay : int | float
        Задержка между попытками, сек.

    Returns
    -------
    Callable
        Декоратор для асинхронной функции запроса.

    Notes
    -----
    - 200/202/204 считаются успешными.
    - 401/403 -> AuthenticationError.
    - 429 при raise_error=True -> ManyRequestsError.
    - Иначе — повторы до исчерпания.
    """
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
