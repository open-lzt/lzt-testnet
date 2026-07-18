<p align="right"><a href="README.en.md">English</a> · <b>Русский</b></p>

# lzt-testnet

**Мок-сервер на FastAPI, воспроизводящий поверхность API `lzt.market` / `lolzteam` для
офлайн-тестирования против [`pylzt`](../aiolzt).** Никаких живых токенов, никаких
реальных денег, никаких рейт-лимитов — и он умеет воспроизводить граничные случаи
(рейт-лимитинг, отзыв токена, неидемпотентную двойную покупку), которые реальный API
не отдаст вам по требованию.

[Документация для AI-агентов](docs/for_ai/index.md) — карта модулей + инварианты, читать перед исходным кодом.

> Приватный репозиторий, часть набора-семейства lolzteam-ecosystem (`pylzt`, `lzt-eventus`,
> `lzt-flow`, `lzt-testnet`). Никаких секретов, никаких реальных токенов — это фейковый сервер.

## Быстрый старт

```bash
cp .env.example .env   # опционально — значения по умолчанию уже подходят
uv sync --extra dev
scripts/run.sh
```

Сервер слушает `http://127.0.0.1:8765` по умолчанию (переопределяется через
`LZT_TESTNET_HOST` / `LZT_TESTNET_PORT`, либо через export, либо в `.env`).

```bash
curl http://127.0.0.1:8765/testnet/health
# {"status":"ok"}
```

## Эксплуатация

| Задача | Команда |
|---|---|
| Сбросить всё состояние в памяти (сервер должен быть запущен) | `scripts/reset.sh` |
| Отозвать bearer-токен посреди сессии | `curl -X POST .../testnet/revoke-token -d '{"token":"..."}'` |
| Проверка здоровья | `curl .../testnet/health` |
| Остановка | Ctrl-C процесса `scripts/run.sh` — состояние только в памяти, чистить нечего |

## Как выводятся ~206 stateless-маршрутов

`src/lzt_testnet/catalog/registry.py` обходит `pylzt.methods` через
`pkgutil.walk_packages`, импортируя каждый подмодуль, чтобы все конкретные подклассы
`BaseMethod` зарегистрировались, затем собирает их рекурсивно через `__subclasses__()`.
`src/lzt_testnet/catalog/route_table.py` превращает каждый собранный класс в
`RouteEntry` — компилируя шаблон пути `__url__` в сопоставимый регэксп и записывая его
HTTP-метод и объявленную модель ответа `__returning__`. Единый catch-all маршрут
(`src/lzt_testnet/api/catch_all.py`, `/{path:path}`) сопоставляет входящие запросы с этой
таблицей и возвращает сгенерированный `polyfactory` фейковый экземпляр модели ответа
сопоставленного метода.

Это означает, что таблица маршрутов **генерируется из собственных типизированных методов
pylzt**, а не копируется вручную — она автоматически отслеживает каталог методов
pylzt по мере их добавления.

## Примеры

Четыре непересекающихся способа работать с этим сервером, соответствующие четырём слоям
тестового набора (см. [`docs/for_ai/index.md`](docs/for_ai/index.md#test-suite-shape) для
полной картины).

### 1. Направить настоящий `pylzt.Client` на него (предполагаемый путь интеграции)

Используйте это в dev/CI `lzt-flow`/`lzt-eventus`, чтобы их собственные тестовые наборы
выполняли настоящий код `pylzt` без живого токена:

```python
from pylzt import Client
from pylzt.config import ClientConfig

client = Client(
    tokens=["fake-token"],
    config=ClientConfig(
        base_url="http://127.0.0.1:8765",
        forum_base_url="http://127.0.0.1:8765",
    ),
)
lot = await client.market.get_lot(item_id=123)
```

Теперь каждый вызов `BaseMethod` проходит через мок-сервер вместо живого API.

### 2. Управлять stateful-жизненным циклом лота напрямую по HTTP

Используйте это при тестировании кода авторинга flow, который зависит от реальной
семантики create/buy (а не только *формы* ответа) — например, чтобы доказать, что ваша
собственная логика ретраев корректно обрабатывает неидемпотентный `fast-buy`:

```bash
curl -X POST http://127.0.0.1:8765/testnet/stateful/lots \
  -H "Authorization: Bearer seller-token" \
  -d '{"category":"games","price":"10.00","currency":"USD","title":"test lot"}'
# {"item_id":1,...}

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 200 — первая покупка успешна

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 404 NotFound — вторая покупка того же item_id, доказывающая, что неидемпотентность не скрыта
```

### 3. Форсировать детерминированный сценарий ошибки

Используйте это для тестирования собственных путей обработки ошибок (retry-on-`RateLimited`,
alert-on-`PaymentFailed`) не дожидаясь, пока реальный API начнёт вести себя неправильно:

```bash
curl -i http://127.0.0.1:8765/market/lot/123 \
  -H "Authorization: Bearer any-token" \
  -H "X-Testnet-Force-Error: rate_limited"
# HTTP/1.1 429 — {"error":"RateLimited","retry_after":1.0}
```

Значения: `rate_limited` (429) · `auth_failed` (401) · `not_found` (404) ·
`transport_error` (500) · `payment_failed` (402). Проверяется до любой мутации состояния,
как на catch-all маршруте, так и на всех 6 stateful-маршрутах.

### 4. Поднять его in-process для собственного тестового набора

Используйте это в CI-задаче, которой нужен настоящий сокет (например, тестирование
клиента, не тестируемого через ASGI-transport) без отдельного процесса для управления:

```python
import threading
import uvicorn
from lzt_testnet.api.app import create_app

config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
# опрашивайте /testnet/health до server.started, затем используйте server.servers[0].sockets[0]
# для привязанного порта — см. полный фикстур в tests/test_lztforge_client_smoke.py.
```

## Аутентификация

Каждый маршрут требует `Authorization: Bearer <token>` — отсутствующий или некорректный
заголовок → 401 `AuthFailed`. `POST /testnet/revoke-token` с телом `{"token": "<bearer-token>"}`
отзывает токен; последующие запросы с ним затем падают с 401, даже если сама строка токена
никогда не была валидна ни против какого реального хранилища учётных данных.

## Конфигурация

`src/lzt_testnet/config.py` — `Settings` (`pydantic-settings`, префикс `LZT_TESTNET_`):

| Переменная | По умолчанию |
|---|---|
| `LZT_TESTNET_HOST` | `127.0.0.1` |
| `LZT_TESTNET_PORT` | `8765` |
| `LZT_TESTNET_LOG_LEVEL` | `INFO` |

## Разработка

Локальная разработка, CI пока не настроен:

```bash
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

## Лицензия

[MIT](LICENSE)
