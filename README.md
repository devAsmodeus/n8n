## О проекте

Этот сервис на FastAPI предназначен для автоматизированной выгрузки и агрегации данных о товарах с маркетплейса Ozon. Он получает ссылку на карточку товара, извлекает SKU и читаемое имя, выполняет поиск по Ozon, собирает список релевантных товаров с ценами, рейтингами и отзывами, а также выгружает ключевую карточку (топ-товар) с изображением, описанием (включая Rich-контент) и характеристиками. Данные могут сохраняться в PostgreSQL и переиспользоваться в течение 7 дней.


## Ключевые возможности

- Получение агрегированных данных по товарам Ozon по ссылке на товар.
- Поддержка типов сортировки: `score` (по релевантности по умолчанию), `new`, `price`, `rating`.
- Извлечение:
  - списка товаров (URL, цена, рейтинг, кол-во отзывов),
  - сводных цен (min/max/avg),
  - названия и главного изображения топ-товара,
  - описания (Rich/HTML) и характеристик (группировано по атрибутам).
- Дедупликация/кеширование в БД: при повторном запросе в течение 7 дней данные возвращаются из БД (если включено сохранение).
- Логирование всех HTTP-запросов и операций с БД в файлы в `src/logs`.
- Повторные попытки HTTP-запросов с экспоненциальной задержкой и обработкой ошибок (401/403/429 и прочие).
- (Опционально) проверка доступа к API по заголовку `X-Secret-Key`.


## Архитектура

- `src/main.py` — инициализация FastAPI-приложения, подключение роутеров.
- `src/routers/ozon.py` — HTTP-эндпоинты для Ozon (`/n8n/ozon/*`).
- `src/repositories/ozon/` — бизнес-логика:
  - `parser_products.py` — парсинг страниц/данных Ozon и преобразование результатов;
  - `requests.py` — низкоуровневые HTTP-запросы к Ozon API/страницам с ретраями и логированием;
  - `database.py` — сохранение/чтение агрегированных результатов в/из PostgreSQL;
  - `format_message.py`, `answer_messages.py`, `tg_bot.py`, `tg_handlers.py` — вспомогательные компоненты для формирования сообщений/интеграции (при необходимости).
- `src/models/` — SQLAlchemy-модели:
  - `ozon.py` — сущности для хранения поисковых результатов и деталей товара;
  - `users.py` — сущности для Telegram-пользователей и оценок (если требуется).
- `src/schemas/universal.py` — Pydantic-схемы ответов API.
- `src/database.py` — подключение к БД (SQLAlchemy Async Engine/Session, базовый класс моделей).
- `src/middleware.py` — middleware проверки секрета в заголовке `X-Secret-Key`.
- `src/config.py` — конфигурация и переменные окружения (Pydantic Settings).
- `src/migrations/` — Alembic-миграции.
- `src/utils/` — общие утилиты (логирование и ретраи).


## Технологии

- FastAPI, Uvicorn — веб-сервер и API.
- SQLAlchemy (async), Alembic — доступ к БД и миграции (PostgreSQL через `asyncpg`).
- aiohttp, BeautifulSoup4 — HTTP и разбор HTML.
- Pydantic Settings — управление конфигурацией через `.env`.


## Требования

- Python 3.11+
- PostgreSQL 13+


## Переменные окружения

Файл `.env` должен находиться в корне проекта (на уровень выше `src`). В нем необходимо указать:

```
SECRET_KEY=секрет-для-заголовка
BOT_TOKEN=токен_бота_если_используется

DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=postgres
DB_NAME=n8n
```

Сформированный URL подключения к БД доступен как `settings.db_url` и имеет вид `postgresql+asyncpg://USER:PASS@HOST:PORT/NAME`.


## Установка и запуск (локально)

1. Создайте и активируйте виртуальное окружение.
2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Примените миграции БД (см. раздел «Миграции» ниже).

4. Запустите сервис (из каталога `src` или укажите путь к приложению):

```bash
python -m uvicorn main:server_app --host 0.0.0.0 --port 8000
```

В `src/main.py` также предусмотрен запуск через `python src/main.py` (используется `uvicorn.run`).


## Миграции (Alembic)

Каталог миграций — `src/migrations`. Alembic сконфигурирован на основании `src/migrations/env.py` и использует метаданные моделей из `src/database.Base`.

- Команда создания новой миграции (автогенерация):

```bash
alembic revision --autogenerate -m "описание изменений"
```

- Применение миграций:

```bash
alembic upgrade head
```

Важно: перед запуском миграций убедитесь, что `.env` содержит корректные настройки подключения к БД.


## Эндпоинты API

- `GET /n8n/ozon/items/search`
  - **Параметры**:
    - `product_url` (str, обязателен): ссылка на товар Ozon. Должна соответствовать `https://ozon.by/product/...`.
    - `sorting_type` (str, необязателен): один из `score` (по умолчанию), `new`, `price`, `rating`.
  - **Ответ** (`src/schemas/universal.ResultResponse`):
    - `error` (bool)
    - `message` (str | null)
    - `results` (object | null) — агрегированные данные по товару и выдаче.

Пример запроса:

```bash
curl -G \
  'http://localhost:8000/n8n/ozon/items/search' \
  --data-urlencode 'product_url=https://ozon.by/product/primer-ssylki-123456' \
  --data-urlencode 'sorting_type=price'
```

Формат `results` при успешной обработке (укороченный пример):

```json
{
  "products_data": [
    {"url": "https://www.ozon.ru/...", "name": "Товар A", "price": 1990, "rating": 4.7, "reviews": 123},
    {"url": "https://www.ozon.ru/...", "name": "Товар B", "price": 2490, "rating": 4.5, "reviews": 87}
  ],
  "currency_prices": {"min_price": 1500.0, "max_price": 3500.0, "avg_price": 2500.0},
  "product_name": "Наиболее популярный товар",
  "product_image": "https://.../image.jpg",
  "description": "Текст описания без HTML",
  "characteristics": {"Общие": ["параметр 1", "параметр 2"]}
}
```

Замечание: в текущей версии роутер обращается к `parser_products.get_product_data_depr`, в то время как реализация устаревшего метода находится в `src/repositories/ozon/database.py`. При необходимости вызов можно изменить на явный импорт из `database.py` (см. раздел «Примечания по коду»).


## Потоки данных и логика

1) Клиент вызывает `GET /n8n/ozon/items/search`.

2) Роутер валидирует параметры и делегирует работу в слой репозитория.

3) Логика репозитория:
   - `parser_products.format_product_name` получает SKU и читаемое имя товара по ссылке на карточку;
   - `parser_products.get_products` запрашивает поисковую страницу Ozon и извлекает товары и фильтры (через `BeautifulSoup`);
   - `parser_products.format_products` агрегирует карточки (цена/рейтинг/отзывы), сводные цены, топ-товар, описание, характеристики (через `parse_details`);
   - `repositories/ozon/database.get_product_data_depr` при включенном сохранении проверяет наличие актуальных данных в БД (`check_exists`):
     - если есть свежая запись (≤7 дней) — возвращает из БД (`get_database_info`),
     - иначе — парсит заново и сохраняет (`upload_products`).

4) Слой `utils` обеспечивает:
   - ретраи HTTP (`retry_decorators.retry_request`),
   - единообразное логирование входящих/исходящих запросов (`log_decorators.save_request_info`).


## Безопасность (опционально)

Чтобы ограничить доступ к API, можно включить middleware проверки секрета в `src/main.py`:

```python
# server_app.add_middleware(SecretKeyCheck)
```

Тогда каждый запрос должен содержать заголовок `X-Secret-Key` со значением `SECRET_KEY` из `.env`, иначе вернется `403`.


## Логирование

- HTTP-запросы сохраняются в `src/logs/requests.log`.
- Операции с БД — в `src/logs/database.log` (если используется соответствующий декоратор).

Файлы создаются автоматически при первом обращении. Формат логов: уровень, дата/время, модуль, сообщение.


## Повтор запросов и обработка ошибок

`utils/retry_decorators.retry_request` выполняет повторные попытки при неуспешных HTTP-ответах с задержками. Особые случаи:

- 200/202/204 — успех, возвращается текст ответа;
- 401/403 — возбуждается `AuthenticationError`;
- 429 — при `raise_error=True` возбуждается `ManyRequestsError`;
- иные статусы — повторяются до исчерпания попыток, затем возбуждается общее исключение или возвращается значение по умолчанию.


## Модель данных (PostgreSQL)

Определена в `src/models/ozon.py`:

- `ozon_search_match` — основная запись запроса/выгрузки:
  - `unique_id` (UUID, PK),
  - `product_url`, `sku_id`, `concat_name`, `sorting_type`,
  - `create_time`, `update_time`.
- `ozon_url_products` — нормализованный список ссылок выдачи:
  - составной PK: (`unique_id`, `sorting_type`, `index`),
  - `product_url`, `product_price`, `product_rating`, `product_reviews`.
- `ozon_product_top` — сводные поля и метаданные топ-товара:
  - составной PK: (`unique_id`, `attribute_name`),
  - `value` (строковое значение; для цен — преобразуется к float при чтении).
- `ozon_product_characteristics` — характеристики топ-товара:
  - составной PK: (`unique_id`, `characteristics_name`),
  - `value` (строковое представление списка значений; при чтении приводится к структуре).

Дополнительно `src/models/users.py` содержит сущности для Telegram-пользователей и оценок (если требуется интеграция).


## Примечания по коду

- В `src/routers/ozon.py` вызов `parser_products.get_product_data_depr(...)` может быть некорректным, т.к. реализация `get_product_data_depr` находится в `src/repositories/ozon/database.py`. При необходимости используйте явный импорт:

```python
from src.repositories.ozon.database import get_product_data_depr
```

- Cookies/заголовки в `parser_products.get_headers` используются для повышения стабильности парсинга. Следите за актуальностью значений.


## Локальная разработка

- Режим автоперезапуска: запускайте Uvicorn с `--reload`.
- Настройка уровня логирования: по умолчанию `DEBUG` для файловых логов, `INFO` для консоли.
- Тестирование эндпоинтов: используйте Swagger UI на `http://localhost:8000/docs` или ReDoc на `http://localhost:8000/redoc`.


## Частые вопросы

- «Почему иногда возвращается пустой результат?» — На стороне Ozon могут меняться разметка и виджеты. Проверьте корректность заголовков/куки и актуальность парсеров (`widgetStates`, селекторы в `BeautifulSoup`).
- «Где менять TTL кеша в БД?» — В `repositories/ozon/database.py` в функции `check_exists` условие `(datetime.now() - update_time).days <= 7`.
- «Как включить защиту по ключу?» — Раскомментируйте middleware `SecretKeyCheck` в `src/main.py` и установите `SECRET_KEY` в `.env`.


## Лицензия

Проект распространяется на условиях внутреннего использования. Права принадлежат владельцу репозитория.


