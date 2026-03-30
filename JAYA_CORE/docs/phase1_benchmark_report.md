# Phase 1 Benchmark Report (JayaIR)

## Scope
Benchmark pipeline for repeated desktop/action intents:
- open desktop
- create/show/move/close window
- search/list/reset related commands

Target metrics:
- warm cache p50/p95 latency
- cache hit-rate under repeated command workload

## Command

```bash
C:/Users/Lenovo/AppData/Local/Programs/Python/Python312/python.exe JAYA_CORE/scripts/benchmark_phase1_ir.py
```

## Benchmark Gate

Normal gate check:

```bash
C:/Users/Lenovo/AppData/Local/Programs/Python/Python312/python.exe JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate
```

Fail-fast gate (non-zero exit on threshold violation):

```bash
C:/Users/Lenovo/AppData/Local/Programs/Python/Python312/python.exe JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate
```

Custom gate thresholds example:

```bash
C:/Users/Lenovo/AppData/Local/Programs/Python/Python312/python.exe JAYA_CORE/scripts/benchmark_phase1_ir.py --gate --max-warm-p50-ms 0.02 --max-warm-p95-ms 0.05 --min-hit-rate 0.95
```

## VS Code Task Integration

Tasks file:
- `.vscode/tasks.json`

Available tasks:
- `JAYA Phase1: Test Core`
- `JAYA Phase1: Benchmark Guard`
- `JAYA Phase1: Benchmark Gate (strict)`
- `JAYA Phase1: Benchmark Snapshot JSON`

## CI Workflow Integration

Workflow file:
- `.github/workflows/phase1-benchmark-gate.yml`

What it does:
- run core Phase 1 tests,
- run benchmark gate tests,
- execute strict benchmark gate,
- upload latest benchmark JSON artifact.

## Sign-Off Flow

Use this report together with:
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`

Phase 1 should be considered complete only after all checklist gates are marked done.

## Results

| Policy | Cold p50 / p95 (ms) | Warm p50 / p95 (ms) | Hit rate | Cache items |
|---|---:|---:|---:|---:|
| cache=128, ttl=120 | 0.0233 / 0.1370 | 0.0159 / 0.0200 | 0.988 | 10 |
| cache=256, ttl=300 | 0.0332 / 0.1313 | 0.0095 / 0.0100 | 0.988 | 10 |
| cache=512, ttl=300 | 0.0207 / 0.0314 | 0.0095 / 0.0098 | 0.988 | 10 |
| cache=768, ttl=600 | 0.0204 / 0.0288 | 0.0094 / 0.0097 | 0.988 | 10 |

## Chosen policy
Use:
- `cache_size = 768`
- `ttl_s = 600.0`

Reason:
- best warm p50 and p95 in this workload,
- stable hit-rate,
- bounded cache remains resource-aware for current workload.

## Notes
- Warm-path optimization was applied so cache hits can skip full validation pass when signature is already compiled.
- Keep rerunning this benchmark as opcode coverage and translator complexity grow.
