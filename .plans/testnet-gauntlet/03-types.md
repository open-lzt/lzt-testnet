# 03 — Types (frozen contract)

Everything a parallel builder needs. Python 3.12, `from __future__ import annotations`. Enums are
`StrEnum` (no string literals). DTOs are `@dataclass(frozen=True, slots=True)` unless they cross the
YAML/HTTP boundary (then pydantic `BaseModel`, matching the repo's mixed convention).

## L1 — `chaos/faults.py`

```python
from enum import StrEnum
from dataclasses import dataclass
import random

class FaultKind(StrEnum):
    # --- transport (pre-response, short-circuit) ---
    HTTP_500 = "http_500"
    HTTP_502_NGINX = "http_502_nginx"      # raw nginx HTML body, not JSON
    HTTP_503 = "http_503"
    HTTP_504 = "http_504"
    RATE_LIMITED_429 = "rate_limited_429"  # + Retry-After header
    AUTH_DROP_401 = "auth_drop_401"        # session "expired" mid-run
    UNKNOWN_ERROR_CODE = "unknown_error_code"  # 4xx with an undocumented body code
    TIMEOUT = "timeout"                    # hang past client timeout then drop
    CONNECTION_DROP = "connection_drop"    # reset before body
    # --- post-response (mutate real response) ---
    SLOW = "slow"                          # add latency, response still valid
    BYZANTINE_MISSING_FIELD = "byzantine_missing_field"  # 200 OK, drop a field
    BYZANTINE_NULL = "byzantine_null"      # 200 OK, null where an object was
    BYZANTINE_WRONG_TYPE = "byzantine_wrong_type"        # 200 OK, wrong type
    MALFORMED_JSON = "malformed_json"      # 200 with unparseable body
    TRUNCATED_BODY = "truncated_body"      # cut Content-Length short
    # --- domain (L2, injected in-handler) ---
    ACCOUNT_INVALID = "account_invalid"
    ALREADY_SOLD = "already_sold"
    RETRY_STORM = "retry_storm"
    CHARGE_THEN_FAIL = "charge_then_fail"
    DELAYED_SETTLEMENT = "delayed_settlement"
    BAD_LOT_CHECK = "bad_lot_check"

PRE_RESPONSE: frozenset[FaultKind]   # the transport short-circuit set
POST_RESPONSE: frozenset[FaultKind]  # the body-mutation set
DOMAIN: frozenset[FaultKind]         # the L2 in-handler set

@dataclass(frozen=True, slots=True)
class Fault:
    kind: FaultKind
    params: dict[str, object]   # e.g. {"retry_after": 1.0, "delay_s": 2.5, "drop_field": "price"}

@dataclass(frozen=True, slots=True)
class FaultContext:
    method: str
    path: str
    seq: int                 # per-app monotonic request ordinal
    endpoint: str            # normalized endpoint key for targeting, e.g. "buy", "list_lots", "*"
    rng: random.Random       # SeedController.stream(seq); the ONLY randomness source a decision may use
```

## L1 — `chaos/seed.py`

```python
from enum import StrEnum
import random

class IdKind(StrEnum):
    LOT = "lot"; PAYMENT = "payment"; SELLER = "seller"; THREAD = "thread"; POST = "post"; USER = "user"

class SeedController:
    def __init__(self, seed: int) -> None: ...
    @property
    def seed(self) -> int: ...
    def stream(self, seq: int) -> random.Random:
        """Independent child RNG for request `seq`: random.Random((self.seed, seq))."""
    def seed_generation(self) -> None:
        """Seed polyfactory ONCE before the first build: ModelFactory.seed_random(self.seed)
        (BaseFactory classmethod — sets __random__=Random(seed) + __faker__.seed_instance(seed); W3.5)."""
    def next_id(self, kind: IdKind) -> int:
        """Seed-scoped, per-app monotonic id — replaces module-global itertools.count (D6/TD-2)."""
    def next_seq(self) -> int:
        """Per-app request ordinal for FaultContext.seq."""
```

## L1 — `chaos/profiles.py`

```python
from enum import StrEnum
from dataclasses import dataclass, field

class Intensity(StrEnum):
    OFF = "off"; CALM = "calm"; FLAKY = "flaky"; HOSTILE = "hostile"; LZT_FRIDAY = "lzt_friday"

@dataclass(frozen=True, slots=True)
class ChaosProfile:
    name: str
    weights: dict[FaultKind, float]                       # relative weights of each fault
    per_endpoint: dict[str, dict[FaultKind, float]] = field(default_factory=dict)  # override by endpoint
    fault_probability: float = 0.0                        # P(any fault) per request; 0 → never

BUILTIN: dict[Intensity, ChaosProfile]   # calm/flaky/hostile/lzt_friday; OFF → not present (no-op)

def profile_for(intensity: Intensity) -> ChaosProfile | None: ...
```

## L1 — `chaos/planner.py`

```python
_LEGACY_NAME_MAP: dict[str, FaultKind]   # {"rate_limited":RATE_LIMITED_429,"auth_failed":AUTH_DROP_401,
                                         #  "transport_error":HTTP_500,"payment_failed":CHARGE_THEN_FAIL,
                                         #  "not_found":ALREADY_SOLD}  (absorbs both old _FORCE_ERROR_MAPs)

class FaultPlanner:
    def __init__(self, profile: ChaosProfile | None) -> None: ...
    def decide(self, ctx: FaultContext, *, x_chaos: str | None, legacy: str | None) -> Fault | None:
        """Arming precedence (01-logic): X-Chaos header → legacy X-Testnet-Force-Error → profile roll.
        Pure given (profile, ctx.rng). Returns None for a clean response."""

def parse_x_chaos(value: str) -> tuple[FaultKind, str | None]:
    """'http_502_nginx@buy' -> (FaultKind.HTTP_502_NGINX, 'buy'); no '@' -> (kind, None). Raises on unknown."""
```

## L1 — `chaos/render.py` + `chaos/middleware.py`

```python
from starlette.types import ASGIApp, Receive, Scope, Send

NGINX_502_HTML: str   # canonical '<html><head><title>502 Bad Gateway</title>...' body

def apply_pre_response(fault: Fault) -> "ResponseEffect":
    """Build the short-circuit response for a PRE_RESPONSE fault (status/body/headers, or a drop signal)."""
def apply_post_response(fault: Fault, status: int, headers, body: bytes) -> tuple[int, list, bytes]:
    """Mutate a real response for a POST_RESPONSE fault (byzantine rewrite / truncate / nginx-502 / delay marker)."""

class FaultInjectionMiddleware:
    def __init__(self, app: ASGIApp) -> None: ...
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pure-ASGI. Fast-path return when chaos OFF and no X-Chaos header. Reads SeedController +
        FaultPlanner from scope['app'].state. CONNECTION_DROP/TIMEOUT operate at the ASGI layer
        (BaseHTTPMiddleware cannot drop a connection — hence pure-ASGI). Confirmed feasible in W3.5."""
```

## L2 — `chaos/domain.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class DomainView:
    """Read-only handle the domain fault needs into the stores (buy/payment/check state)."""
    item_id: int | None
    token: str
    was_bought: bool

class DomainOutcome(StrEnum):
    PROCEED = "proceed"; FAIL_INVALID = "fail_invalid"; ALREADY_SOLD = "already_sold"
    TRANSIENT_RETRY = "transient_retry"; CHARGE_THEN_FAIL = "charge_then_fail"; PENDING = "pending"

def maybe_inject(ctx: FaultContext, fault: Fault | None, view: DomainView) -> DomainOutcome:
    """Decide the domain outcome for a buy/check. retry_storm uses a seed-scoped per-item counter so the
    first N attempts return TRANSIENT_RETRY then PROCEED — deterministic by seed."""
```

## L3 — `world/models.py`, `world/stores.py`, `world/builder.py`

```python
from dataclasses import dataclass, field
from enum import StrEnum
from datetime import datetime

class SellerQuality(StrEnum):
    GOOD = "good"; SPAM = "spam"

@dataclass(slots=True)
class SellerRecord:
    seller_id: int
    token: str
    username: str
    quality: SellerQuality
    reputation: int
    lot_ids: list[int] = field(default_factory=list)

@dataclass(slots=True)
class ForumUser:  user_id: int; username: str; reputation: int; joined_at: datetime
@dataclass(slots=True)
class ForumThread: thread_id: int; author_id: int; title: str; created_at: datetime; post_ids: list[int]
@dataclass(slots=True)
class ForumPost:  post_id: int; thread_id: int; author_id: int; body: str; created_at: datetime

class SellerStore:   # dict[int, SellerRecord] + cursor list(), mirrors LotStore
    def get(self, seller_id: int) -> SellerRecord | None: ...
    def by_token(self, token: str) -> SellerRecord | None: ...
    def list(self, quality: SellerQuality | None, cursor: int | None, limit: int) -> tuple[list[SellerRecord], int | None]: ...
class ForumStore:    # users/threads/posts dicts + cursor lists
    ...

class WorldBuilder:
    def __init__(self, seed: int, config: "WorldConfig") -> None: ...
    def populate(self, *, sellers: SellerStore, forum: ForumStore) -> None:
        """EAGER but SMALL: fill the seller roster (good + spam) and the forum. Lots are NOT
        pre-populated — they are lazily materialized (see Materializer, D11)."""


class Materializer:
    """Lazy lot inventory: generate+persist a lot the first time its page is fetched, serve the
    persisted (mutable) record on refetch. Query-keyed identity so refetch is byte-stable (D11)."""

    def __init__(self, seed: int, generator: FakeGenerator, lots: "LotStore",
                 sellers: SellerStore, scenario: "ScenarioStore", config: "WorldConfig") -> None: ...

    def stable_id(self, category: str, index: int) -> int:
        """Deterministic id for item #index in `category` — a function of (seed, category, index),
        NOT SeedController.next_id (which is call-order-dependent and would break refetch stability)."""

    def page(self, *, category: str, cursor: int, limit: int) -> list["LotRecord"]:
        """Materialize-on-fetch: for index in [cursor, cursor+limit), take the stable id; if absent from
        `lots`, generate a seeded record (Random(f'{seed}:{category}:{index}'), seller assigned by
        seeded quality) and persist it; skip ids already bought. Returns the persisted records — so a
        buy between two fetches removes the item from the second page."""

    def seller_of(self, item_id: int) -> SellerRecord:
        """The (seeded) owning seller of a materialized lot."""

    def lot_check_fails(self, item_id: int) -> bool:
        """True iff the lot's owning seller is SPAM — the deterministic BAD_LOT_CHECK / blacklist signal.
        Works for a lazily-materialized lot (materializes it if not yet seen)."""

@dataclass(frozen=True, slots=True)
class WorldConfig:
    roster_size: int = 12
    spam_ratio: float = 0.4
    lots_per_spam_seller: int = 50
    forum_users: int = 30
    forum_threads: int = 20
```

## L4 — `chaos/scenario.py`, `chaos/report.py`

```python
from pydantic import BaseModel

class ScenarioSpec(BaseModel):
    name: str
    seed: int
    intensity: Intensity = Intensity.HOSTILE
    weights: dict[FaultKind, float] | None = None          # overrides the intensity's built-in weights
    per_endpoint: dict[str, dict[FaultKind, float]] = {}
    world: WorldConfig | None = None
    oracle: bool = False

def load_scenario(name: str, *, root: str = "scenarios") -> ScenarioSpec:
    """Read scenarios/<name>.yaml, validate against ScenarioSpec, return it. Raises ScenarioError on bad yaml/schema."""

@dataclass(frozen=True, slots=True)
class FailedProbe:
    seq: int; path: str; fault: FaultKind; seed: int; detail: str

class GauntletRecorder:                       # lives on app.state
    def record(self, ctx: FaultContext, fault: Fault) -> None: ...
    def report(self) -> "GauntletReport": ...

@dataclass(frozen=True, slots=True)
class GauntletReport:
    seed: int
    injected: int
    survived: int
    failed: list[FailedProbe]
    def as_scorecard(self) -> str: ...        # human-readable table
```

## Config + errors (modified)

```python
# config.py — Settings gains (D2)
chaos_mode: Intensity = Intensity.OFF
chaos_seed: int = 0
chaos_scenario: str | None = None
# errors.py — add
class ScenarioError(Exception): ...           # bad/missing scenario yaml
class UnknownFaultError(Exception): ...        # X-Chaos names an unknown fault
```

## Test helpers — `tests/helpers/gauntlet.py`

```python
import httpx
def chaos_client(*, scenario: str | None = None, mode: Intensity = Intensity.OFF, seed: int = 0) -> httpx.AsyncClient:
    """Builds the armed app + httpx.AsyncClient over ASGITransport(app, raise_app_exceptions=False) so
    connection_drop (a raise after response.start) surfaces as a truncated Response, not an exception (W3.5/R3)."""
async def assert_survives(scenario: str, script) -> GauntletReport:
    """Run `script(client)` under the scenario; assert no unhandled 5xx crash of the harness; return the scorecard."""
async def assert_idempotent(client, buy_call) -> None:
    """Under retry_storm, run buy_call to convergence; assert exactly one PaymentRecord for the item."""
async def assert_blacklists(client, list_call, check_call) -> None:
    """Assert spam-seller lots are present in listing AND deterministically fail check_call."""
async def run_oracle(script, *, scenario: str) -> bool:
    """Run `script` under OFF and under `scenario`; return True iff terminal store state matches (eventual correctness)."""
```
