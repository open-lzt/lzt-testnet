<p align="right"><a href="README.en.md">English</a> · <b>Русский</b></p>

# lzt-testnet

Мок-сервер API `lzt.market` на FastAPI. Тестируйте код против [pylzt](https://github.com/open-lzt/pylzt) без живого токена, без денег, без рейт-лимитов.

Умеет то, чего боевой API не даст по требованию: 429, отзыв токена, повторную покупку одного лота.

```bash
uv sync --extra dev
scripts/run.sh
curl http://127.0.0.1:8765/testnet/health
# {"status":"ok"}
```

## Установка

Нужен [uv](https://docs.astral.sh/uv/) и Python 3.12+.

```bash
git clone https://github.com/open-lzt/lzt-testnet.git
cd lzt-testnet
cp .env.example .env      # опционально, дефолты рабочие
uv sync --extra dev
```

Запуск:

```bash
scripts/run.sh                              # 127.0.0.1:8765
scripts/run.sh --host 0.0.0.0 --port 9100
uv run python -m lzt_testnet.cli --port 9100   # то же самое напрямую
```

## Подключить pylzt

В pytest — одна фикстура. Плагин ставится вместе с пакетом, мок поднимается in-process через ASGI, сокет не нужен.

```python
async def test_autobuy(testnet_client):      # уже настроенный pylzt.Client
    lot = await testnet_client.market.get_lot(item_id=123)
```

Вне pytest:

```python
from pylzt import Client, ClientConfig

client = Client.from_token("fake-token", config=ClientConfig.for_testnet())
lot = await client.market.get_lot(item_id=123)
```

Дальше каждый вызов `BaseMethod` идёт в мок, а не в живой API.

## Форсировать ошибку

Заголовок `X-Testnet-Force-Error` проверяется до любой мутации состояния — и на catch-all маршруте, и на всех 6 stateful-маршрутах.

```bash
curl -i http://127.0.0.1:8765/market/lot/123 \
  -H "Authorization: Bearer any-token" \
  -H "X-Testnet-Force-Error: rate_limited"
# HTTP/1.1 429 — {"error":"RateLimited","retry_after":1.0}
```

| Значение | Ответ |
|---|---|
| `rate_limited` | 429 |
| `auth_failed` | 401 |
| `not_found` | 404 |
| `transport_error` | 500 |
| `payment_failed` | 402 |

## Stateful-лоты

Реальная семантика create/buy, а не только форма ответа. Так проверяется, что ваши ретраи не ломаются об неидемпотентный `fast-buy`.

```bash
curl -X POST http://127.0.0.1:8765/testnet/stateful/lots \
  -H "Authorization: Bearer seller-token" \
  -d '{"category":"games","price":"10.00","currency":"USD","title":"test lot"}'
# {"item_id":1,...}

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 200 — первая покупка

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 404 NotFound — второй раз тот же лот
```

## Аутентификация

Каждый маршрут требует `Authorization: Bearer <token>`. Нет заголовка или он битый → 401 `AuthFailed`.

```bash
curl -X POST http://127.0.0.1:8765/testnet/revoke-token -d '{"token":"buyer-token"}'
# дальше все запросы с этим токеном → 401
```

Строка токена ни с чем не сверяется — валидно всё, что не отозвано.

## Эксплуатация

| Задача | Команда |
|---|---|
| Сбросить состояние | `scripts/reset.sh` |
| Здоровье | `curl http://127.0.0.1:8765/testnet/health` |
| Остановка | `Ctrl-C` — состояние только в памяти, чистить нечего |

## Конфигурация

`src/lzt_testnet/config.py`, `pydantic-settings`, префикс `LZT_TESTNET_`.

| Переменная | По умолчанию |
|---|---|
| `LZT_TESTNET_HOST` | `127.0.0.1` |
| `LZT_TESTNET_PORT` | `8765` |
| `LZT_TESTNET_LOG_LEVEL` | `INFO` |
| `LZT_TESTNET_CONTROL_KEY` | пусто — ключ для `/testnet/*` маршрутов |

## Откуда берутся ~206 маршрутов

Таблица маршрутов **генерируется из типизированных методов pylzt**, а не копируется руками — новый метод в pylzt появляется здесь сам.

- `catalog/registry.py` — обходит `pylzt.methods` через `pkgutil.walk_packages`, собирает подклассы `BaseMethod`.
- `catalog/route_table.py` — класс → `RouteEntry`: шаблон `__url__` в регэксп, HTTP-метод, модель ответа `__returning__`.
- `api/catch_all.py` — маршрут `/{path:path}` сопоставляет запрос с таблицей и отдаёт фейковый экземпляр модели, сгенерированный `polyfactory`.

## Свой сокет вместо ASGI

Для CI-задачи, которой нужен настоящий порт:

```python
import threading
import uvicorn
from lzt_testnet.api.app import create_app

config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
threading.Thread(target=server.run, daemon=True).start()
# ждите server.started, порт — в server.servers[0].sockets[0]
```

Готовая фикстура — `tests/test_lztforge_client_smoke.py`.

## Разработка

```bash
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

[Документация для AI-агентов](docs/for_ai/index.md) — карта модулей и инварианты, читать перед исходниками.

## Экосистема

[pylzt](https://github.com/open-lzt/pylzt) · [auto-lzt](https://github.com/open-lzt/auto-lzt) · [lzt-eventus](https://github.com/open-lzt/lzt-eventus) · [lzt-mcp](https://github.com/open-lzt/lzt-mcp) · [весь стенд](https://github.com/open-lzt/open-lzt)

## Лицензия

[MIT](LICENSE)
