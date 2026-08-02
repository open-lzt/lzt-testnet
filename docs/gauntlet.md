<p align="right"><a href="gauntlet.en.md">English</a> · <b>Русский</b></p>

# Gauntlet — стенд хаоса для плагинов lzt.market

Мок testnet по умолчанию отдаёт счастливый путь. Gauntlet делает его враждебным: подсовывает те отказы, которыми в вас кидается настоящий маркет — 502, отвалившуюся авторизацию, византийские ответы, гонки «уже продано», штормы ретраев. Всё это управляется **одним seed**, поэтому падение воспроизводится, а CI детерминирован.

**По умолчанию выключен.** Пока вы его не взвели, мок остаётся чистым и существующий набор тестов не меняется.

## Три способа взвести

**1. Глобально, из CLI или окружения** — весь сервер работает враждебно:

```bash
./scripts/run.sh --chaos hostile --seed 42
# или именованный сценарий:
./scripts/run.sh --scenario nginx-down
# то же самое через переменные:
LZT_TESTNET_CHAOS_MODE=hostile LZT_TESTNET_CHAOS_SEED=42 ./scripts/run.sh
```

Интенсивность по нарастающей: `calm` → `flaky` → `hostile` → `lzt_friday`.

**2. На один запрос, из юнит-теста** — заголовок `X-Chaos` вызывает ровно один детерминированный сбой:

```
X-Chaos: http_502_nginx@*      # сырой 502 от nginx на любом маршруте
X-Chaos: rate_limited_429@*    # 429 с Retry-After
X-Chaos: account_invalid@buy   # покупка «прошла», но аккаунт невалиден
X-Chaos: retry_storm@buy       # первые N покупок временно падают, потом сходятся
```

`kind@endpoint` бьёт по одному эндпоинту (`buy`, `list_lots`, `payments`), а `kind` или `kind@*` — по всем. Полный список сбоев — енум `FaultKind` в `src/lzt_testnet/chaos/faults.py`.

**3. Именованный сценарий** — взвешенное меню сбоев плюс необязательный stateful-мир, YAML в `scenarios/`. В комплекте: `black-friday-meltdown`, `auth-expiry-storm`, `seller-spam-flood`, `nginx-down`, `pagination-hell`. Схема — в `scenarios/README.md`.

## Как читать карточку результата

Каждый внедрённый сбой записывается. После прогона `app.state.recorder.report().as_scorecard()` печатает:

```
Gauntlet scorecard (seed=502)
  injected: 51
  survived: 49
  failed:   2
    seq=17 path=/testnet/stateful/lots/3/buy fault=charge_then_fail — double charge
```

Провалившаяся проба несёт точные `seed`, номер запроса `seq` и `fault`. Перезапуск с тем же seed выстрелит тем же сбоем в той же точке.

## Помощники для автора плагина (`tests/helpers/gauntlet.py`)

```python
from tests.helpers.gauntlet import assert_idempotent, assert_blacklists, assert_survives, run_oracle

report = await assert_survives("nginx-down", my_client_script)   # гоняет сценарий, отдаёт карточку
await assert_idempotent(client, buy, item_id=id, token=tok)      # retry_storm → ровно один платёж
await assert_blacklists(client)                                  # лоты спам-продавца не проходят проверку
```

### Дифференциальный оракул

Главная проверка: прогнать **один и тот же** клиентский сценарий начисто и под хаосом. Корректный, то есть идемпотентный, клиент приходит к **одному и тому же деловому результату** в обоих случаях.

```python
assert await run_oracle(my_script, seed=1) is True    # идемпотентный клиент сходится
```

Неидемпотентный клиент разъезжается, и `run_oracle` возвращает `False`. Это оракул поймал настоящий баг, которого счастливый путь не увидел бы никогда.

## Долгий прогон

```bash
./scripts/gauntlet-soak.sh nginx-down 200 502   # сценарий, число запросов, seed → базовая линия сбоев в секунду
```

## Про детерминированные id

Ловушка: id лотов и платежей привязаны к seed **в пределах экземпляра приложения** — для каждого `create_app()` они начинаются с `1`, а не сквозные по процессу. Так и задумано: id воспроизводимы от прогона к прогону. На один долгоживущий сервер это не влияет, а каждый тест получает свежую детерминированную последовательность.
