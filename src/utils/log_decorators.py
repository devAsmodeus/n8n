import inspect
import logging
import os

from functools import wraps
from typing import Callable
from pathlib import Path


class CustomFileHandler(logging.FileHandler):
    def emit(self, record):
        if record.levelno in (logging.WARNING, logging.ERROR, logging.CRITICAL, logging.INFO, logging.DEBUG):
            super().emit(record)


def save_request_info(function: Callable) -> Callable:
    """
    Декоратор логирования HTTP-запросов: пишет статус и URL в файл логов.

    Parameters
    ----------
    function : Callable
        Целевая асинхронная функция, выполняющая HTTP-запрос и возвращающая (url, status, text).

    Returns
    -------
    Callable
        Обернутая функция, которая в случае успеха пишет DEBUG-лог, а при исключении — ERROR.
    """
    @wraps(function)
    async def wrapper(*args, **kwargs) -> str:
        file_path = 'src/logs/requests.log'
        create_log_file(file_path)
        logger = get_logger(file_path)
        file_path = inspect.getfile(function)
        try:
            url, status, text = await function(*args, **kwargs)
        except Exception as exception:
            logger.error(f"{file_path}\\{function.__name__}: {exception}")
            raise exception
        else:
            logger.debug("{} {}".format(status, url))
            return text

    return wrapper


def save_database_info(function: Callable) -> Callable:
    """
    Декоратор логирования операций с БД.

    Parameters
    ----------
    function : Callable
        Асинхронная функция работы с БД.

    Returns
    -------
    Callable
        Обернутая функция с логированием успеха/ошибок.
    """
    @wraps(function)
    async def wrapper(*args, **kwargs) -> str:
        file_path = 'src/logs/database.log'
        create_log_file(file_path)
        logger = get_logger(file_path)
        file_path = inspect.getfile(function)
        try:
            result = await function(*args, **kwargs)
        except Exception as exception:
            logger.error(f"{file_path}\\{function.__name__}: {exception}")
            raise exception
        else:
            logger.debug("Successfully database connection")
            return result

    return wrapper


def get_logger(log_file: str) -> logging.Logger:
    """
    Создает/возвращает настроенный `logging.Logger` с файловым хендлером.

    Parameters
    ----------
    log_file : str
        Путь до файла логов относительно корня проекта.

    Returns
    -------
    logging.Logger
        Инициализированный логгер с уровнем DEBUG.
    """
    logger = logging.getLogger(__name__)
    if logger.hasHandlers():
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
    logger.setLevel(logging.DEBUG)
    project_path = Path(__file__).resolve().parent.parent.parent
    file_handler = CustomFileHandler(os.path.join(project_path, log_file))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(asctime)s - %(message)s',
        encoding='windows-1251'
    )
    return logger


def create_log_file(full_path: str) -> None:
    """
    Гарантирует существование каталога и файла логов.

    Parameters
    ----------
    full_path : str
        Относительный путь вида `src/logs/<file>.log`.
    """
    dir_name, _, file_name = full_path.rpartition('/')
    project_path = Path(__file__).resolve()
    while not str(project_path).endswith('n8n'):
        project_path = project_path.parent
    else:
        log_dir = project_path / dir_name
        log_file = log_dir / file_name
        log_dir.mkdir(exist_ok=True)
        log_file.touch(exist_ok=True)
