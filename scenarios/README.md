# Gauntlet scenarios

Named chaos scenarios, as data. Each `*.yaml` here validates against `ScenarioSpec`
(`src/lzt_testnet/chaos/scenario.py`) and can be armed with:

```bash
python -m lzt_testnet.cli --scenario nginx-down
```

## Schema

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | — | scenario id (should match the file name) |
| `seed` | int | `0` | the determinism seed — same seed ⇒ same fault + data sequence |
| `intensity` | `off`/`calm`/`flaky`/`hostile`/`lzt_friday` | `hostile` | base fault menu + rate |
| `fault_probability` | float | intensity's | P(any fault) per request, overrides the intensity |
| `weights` | map<fault, float> | intensity's | relative weight of each fault; overrides the base menu |
| `per_endpoint` | map<endpoint, map<fault, float>> | `{}` | weight overrides for `buy` / `list_lots` / `payments` |
| `world` | `WorldConfig` | none | arm the stateful roster + forum (`roster_size`, `spam_ratio`, …) |
| `oracle` | bool | `false` | run the differential-oracle for this scenario |

Fault names are the `FaultKind` values (e.g. `http_502_nginx`, `byzantine_missing_field`,
`retry_storm`). An unknown name fails validation — CI rejects the PR.

## Contributing a scenario

1. Copy an existing file, rename it, set a distinct `name`/`seed`.
2. Pick weights that tell a story (see `nginx-down` for a single dominant fault,
   `pagination-hell` for per-endpoint corruption).
3. Run `pytest tests/chaos/test_scenario.py` — it loads and validates every shipped file.
