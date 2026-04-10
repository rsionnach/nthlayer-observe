# P5 Generate Cleanup Plan

## Context

Phases 0-4 of the nthlayer-observe migration are complete. Code was **copied** to observe (not moved) — generate's files are untouched. This plan lists every file to remove from generate, every import to update, and the test strategy.

**Execute as a separate bead in a fresh session with its own test gate.**

## Scope Revision (2026-04-08)

Original plan included removing `discovery/` and `dependencies/` from generate. Audit found both are still load-bearing:

- **discovery/** — used by `dashboards/resolver.py` (metric validation) and `metrics/discovery.py` (recommendations)
- **dependencies/** (providers + discovery.py) — used by `cli/topology.py`, `topology/enrichment.py`, `slos/correlator.py`

These stay in generate. P5 removes only `drift/` and `verification/` (Phase 3 duplicates with zero or optional-only non-CLI consumers).

CLI strategy: **remove entirely** (no try/except fallbacks, no redirect stubs). Users use `nthlayer-observe` for runtime operations.

## Pre-conditions

- nthlayer-observe: 286 tests passing, 9 CLI commands, all boundaries verified
- nthlayer-generate: untouched, all tests should still pass
- No cross-package imports in either direction

## Files to Remove from Generate

### Phase 3 duplicates (now in observe)

**drift/** (entire directory — 868 lines):
- `src/nthlayer/drift/__init__.py`
- `src/nthlayer/drift/analyzer.py`
- `src/nthlayer/drift/models.py`
- `src/nthlayer/drift/patterns.py`

**verification/** (entire directory — 739 lines):
- `src/nthlayer/verification/__init__.py`
- `src/nthlayer/verification/models.py`
- `src/nthlayer/verification/extractor.py`
- `src/nthlayer/verification/verifier.py`
- `src/nthlayer/verification/exporter_guidance.py`

### CLI files (commands moved to observe)

- `src/nthlayer/cli/drift.py` — now `nthlayer-observe drift`
- `src/nthlayer/cli/verify.py` — now `nthlayer-observe verify`
- `src/nthlayer/cli/deps.py` — now `nthlayer-observe dependencies`
- `src/nthlayer/cli/blast_radius.py` — now `nthlayer-observe blast-radius`

### NOT removed (still used by generate)

| Module | Consumer | Reason |
|--------|----------|--------|
| `discovery/` | `dashboards/resolver.py`, `metrics/discovery.py` | Metric validation + recommendations |
| `dependencies/` | `cli/topology.py`, `topology/enrichment.py`, `slos/correlator.py` | Topology export + correlation |
| `slos/gates.py` | `cli/deploy.py`, `generators/backstage.py` | Deploy gate checks |
| `slos/correlator.py` | `slos/gates.py`, `cli/deploy.py` | Deployment correlation |
| `policies/` | Gates, API, deploy CLI | Policy evaluation chain |
| `api/` | Webhook receivers, policy audit, teams | FastAPI infrastructure |
| `db/` | SLO storage, audit, API, correlator | Persistence layer |
| `deployments/` | `api/routes/webhooks.py`, `slos/deployment.py` | Webhook processing |

## Tests to Remove

| Test File | Action |
|-----------|--------|
| `tests/test_drift.py` | Remove (observe has equivalent) |
| `tests/test_verification.py` | Remove (observe has equivalent) |
| `tests/test_cli_blast_radius.py` | Remove (CLI file removed) |
| `tests/test_cli_dependencies.py` | Remove (CLI file removed) |

## Files to Update

### `src/nthlayer/demo.py` (main CLI router)

- Remove imports: `handle_drift_command`, `register_drift_parser`, `handle_verify_command`, `register_verify_parser`, `handle_deps_command`, `register_deps_parser`, `handle_blast_radius_command`, `register_blast_radius_parser`
- Remove parser registrations for verify, drift, deps, blast-radius
- Remove command dispatch blocks for verify, drift, deps, blast-radius
- Remove `--include-drift` and `--drift-window` args from deploy parser
- Remove `include_drift`/`drift_window` from `deploy_check_command()` call
- Remove "nthlayer verify" from help text

### `src/nthlayer/cli/deploy.py`

- Remove `from nthlayer.drift import ...` (line 16)
- Remove `include_drift`/`drift_window` parameters from `deploy_check_command()` signature
- Remove `_check_drift()` function
- Remove `_display_drift_summary()` function
- Remove drift severity escalation in `_format_result()`

### `src/nthlayer/cli/portfolio.py`

- Remove `from nthlayer.drift import ...` (line 30)
- Remove `_collect_drift_data()` function
- Remove drift-related parameters and display code

### `pyproject.toml`

- Remove `scipy` from dependencies (only used by drift/)
- Remove `numpy` from dependencies (only used by drift/)
- Remove or empty `drift-ml` optional dependency group

## Execution Order

1. Create feature branch `p5-generate-cleanup`
2. Delete `drift/` and `verification/` directories
3. Delete 4 CLI files (drift, verify, deps, blast_radius)
4. Delete 4 test files
5. Update `demo.py` — remove imports, registrations, dispatch, drift args
6. Update `cli/deploy.py` — strip all drift logic
7. Update `cli/portfolio.py` — strip all drift logic
8. Update `pyproject.toml` — remove scipy, numpy
9. Run tests and fix any remaining broken imports

## Verification

1. `uv run pytest tests/ -v --tb=short -x` — all remaining tests pass
2. `uv run ruff check src/ tests/ --ignore E501` — no lint errors
3. `uv pip install -e .` works without scipy/numpy
4. `nthlayer --help` — drift, verify, deps, blast-radius absent
5. `nthlayer check-deploy --help` — no `--include-drift`/`--drift-window`
6. `nthlayer topology --help` — still works
7. `nthlayer generate --help` — still works

## AC

1. `drift/` and `verification/` directories deleted from generate
2. 4 CLI commands removed (drift, verify, deps, blast-radius)
3. Deploy and portfolio commands work without drift features
4. Generate test suite passes (minus removed test files)
5. `pip install -e .` works with reduced deps (no scipy/numpy)
6. No broken imports in remaining generate code
