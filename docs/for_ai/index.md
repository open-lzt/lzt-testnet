<p align="right"><a href="index.en.md">English</a> · <b>Русский</b></p>

# lzt-testnet — карта модулей для AI-агентов

Читайте это перед тем, как открывать исходный код в этом репозитории. Порядок слоёв
соответствует конвенции `open-lzt` (фича-колокация, без свалок `utils.py`).

## Структура

```
src/lzt_testnet/
├── config.py               Settings (pydantic-settings, префикс LZT_TESTNET_)
├── errors.py                иерархия TestnetError — каждый маршрут поднимает их, никогда голый Exception
├── catalog/
│   ├── registry.py          collect_base_methods() — обходит pylzt.methods, возвращает каждый
│   │                        конкретный подкласс BaseMethod (pkgutil.walk_packages + __subclasses__)
│   └── route_table.py       RouteEntry/RouteTable/build_route_table — превращает собранные методы
│                            в таблицу линейного сканирования (path_pattern, http_method) -> RouteEntry.
│                            Пропускает методы с пустым __url__ (составные пагинационные хелперы
│                            вроде ListLotsPage/GetLotsBatch, у которых нет собственного маршрута)
├── fake/
│   └── generator.py         FakeGenerator — оборачивает polyfactory ModelFactory для каждой Pydantic-модели,
│                            кэшируется по классу модели, переопределения побеждают сгенерированные значения
├── state/
│   ├── lot_store.py          LotStore — dict[item_id, LotRecord] в памяти, курсорная пагинация
│   ├── payment_store.py      PaymentStore — list[PaymentRecord] в памяти, курсорная пагинация
│   └── scenario_store.py     ScenarioStore — отозванные токены + отслеживание купленных товаров (неидемпотентность)
└── api/
    ├── app.py                create_app() — корень композиции; подключает хранилища к app.state,
    │                        регистрирует обработчики ошибок + все роутеры (порядок важен: catch_all
    │                        последний, так как это wildcard-маршрут `/{path:path}`)
    ├── dependencies.py       get_bearer_token, force_error_header — функции FastAPI Depends
    ├── error_handlers.py     register_error_handlers(app) — один @app.exception_handler на каждый
    │                        подкласс TestnetError, сопоставляет с фиксированной таблицей HTTP-статусов
    ├── catch_all.py          Общий диспетчер на ~206 маршрутов — сопоставляет RouteTable, строит
    │                        фейковый ответ через FakeGenerator, подставляет параметры пути в него
    ├── stateful.py            6 эндпоинтов с реальной семантикой под /testnet/stateful/* — единственные
    │                        маршруты с реальной логикой мутации (create/list/bump/set-price/
    │                        fast-buy/payments)
    └── control.py             /testnet/reset, /testnet/revoke-token — плоскость управления тестовым стендом
```

## Инварианты, которые нужно знать перед редактированием

- `RouteTable.match` — это **линейное сканирование по первому совпадению**: если два
  `BaseMethod` разделяют идентичный шаблон пути, побеждает тот, что был собран первым; это
  реальная неоднозначность, а не баг (см. комментарий в `tests/test_all_methods_roundtrip.py`).
  Любой новый тест stateless-маршрута должен проверяться против *фактически совпавшего*
  `RouteEntry`, а не того метода, который он намеревался проверить.
- `fast-buy` намеренно **неидемпотентен**: покупка дважды возвращает `NotFound` во второй раз
  (лот исчезает из `LotStore`, а `ScenarioStore.bought_item_ids` запоминает это независимо от
  хранилища, так что форсированный ретрай `payment_failed` всё равно видит корректное состояние).
- `X-Testnet-Force-Error` проверяется **до любого чтения/мутации состояния**, как в
  `catch_all.py`, так и в каждом обработчике `stateful.py` (через общий хелпер
  `_raise_forced_error` в `stateful.py`).
- `catalog/registry.py` требует `import pylzt` (а не только `import pylzt.methods`) перед
  обходом `__subclasses__()` — иначе фасадные подмодули (`market.py`/`forum.py`/`antipublic.py`)
  могут ещё не успеть зарегистрировать свои подклассы `BaseMethod`.
- `[tool.uv.sources] pylzt = { path = "../aiolzt" }` в `pyproject.toml` резолвится
  относительно того места, где физически лежит `pyproject.toml` — ломается внутри `git worktree`
  под `.worktrees/<name>/` (на два уровня глубже корня репозитория). Обходной путь, использованный
  при исходной сборке: локальная junction-ссылка `.worktrees/aiolzt -> ../../aiolzt`, не
  отслеживаемая git.

## Форма тестового набора

- `test_stateless_roundtrip.py` — фиксированная выборка из 20 методов, быстрая, in-process
  (`httpx.ASGITransport`).
- `test_all_methods_roundtrip.py` — каждый собранный метод, автогенерируемая (без захардкоженного
  списка имён), in-process.
- `test_all_methods_e2e.py` — каждый собранный метод, прогоняется через **настоящий сокет** против
  `uvicorn`-сервера, поднятого в фоновом потоке (фикстура на уровне модуля, один запуск на файл).
- `test_lztforge_client_smoke.py` — настоящий, немодифицированный `pylzt.Client` против живого
  сокета; доказывает, что `ClientConfig(base_url=...)` не требует monkeypatch.
- `test_stateful_lot_lifecycle.py` / `test_payments_feed.py` / `test_error_injection.py` — реальная
  логика мутации 6 stateful-эндпоинтов.
