# nthlayer-observe

**Deterministic runtime infrastructure for the NthLayer ecosystem.**

Reads live system state from Prometheus and OpenSRM manifests. Produces structured assessments: error budgets, drift projections, deployment gate decisions, metric verification, dependency discovery, blast radius analysis, portfolio health, and reliability scorecards.

[![Status: Alpha](https://img.shields.io/badge/Status-Alpha-orange?style=for-the-badge)](https://github.com/rsionnach/nthlayer-observe)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue?style=for-the-badge)](LICENSE)

## TL;DR

```bash
pip install nthlayer-observe
```

---

## What This Is

nthlayer-observe is the **runtime assessment layer** in the OpenSRM ecosystem. While [nthlayer](https://github.com/rsionnach/nthlayer) is a pure compiler (manifests → artifacts), nthlayer-observe connects to live infrastructure and produces assessments about current state.

```
OpenSRM Manifests + Prometheus
         │
         ▼
  nthlayer-observe
         │
         ├── collect     → Error budget assessments
         ├── drift       → Budget exhaustion projections
         ├── verify      → Metric existence checks
         ├── check-deploy → Deployment gate decisions
         ├── blast-radius → Impact analysis
         ├── portfolio   → Org-wide health aggregation
         └── scorecard   → Per-service reliability scores
```

Every command is **deterministic** — same inputs produce same outputs. No LLM, no reasoning, no judgment. Pure arithmetic on live data.

---

## ⚡ Core Features

### Error Budget Collection

Query Prometheus, calculate budget consumption against OpenSRM SLO targets.

```bash
$ nthlayer-observe collect \
    --specs-dir manifests/ \
    --prometheus-url http://prometheus:9090

payment-api:
  availability: 73.2% budget remaining (HEALTHY)
  latency_p99: 45.1% budget remaining (WARNING)

checkout-service:
  availability: 12.8% budget remaining (CRITICAL)
```

### Drift Detection

Predict SLO exhaustion before it happens. Uses linear regression on error budget burn rate.

```bash
$ nthlayer-observe drift \
    --service payment-api \
    --prometheus-url http://prometheus:9090

payment-api: CRITICAL
  Current: 73.2% budget remaining
  Trend: -2.1%/day (gradual decline)
  Projection: Budget exhausts in 23 days

  Recommendation: Investigate error rate increase before next release
```

### Deployment Gates

Block deploys when error budget is exhausted or drift is critical. Reads from the assessment store — no live Prometheus query at gate time.

```bash
$ nthlayer-observe check-deploy --service payment-api

✗ BLOCKED
  Error budget: exhausted (-47 minutes)
  Exit code: 2
```

Exit codes: `0` = approved, `1` = warning, `2` = blocked.

### Metric Verification

Verify that all SLO metrics declared in OpenSRM manifests actually exist in Prometheus.

```bash
$ nthlayer-observe verify \
    --specs-dir manifests/ \
    --prometheus-url http://prometheus:9090

payment-api:
  ✓ http_requests_total         FOUND
  ✓ http_request_duration_seconds FOUND
  ✗ http_server_active_requests MISSING
```

### Blast Radius Analysis

Understand impact before making changes. Walks the dependency graph from OpenSRM manifests.

```bash
$ nthlayer-observe blast-radius --service payment-api

Direct dependents (3):
  • checkout-service (critical) — 847K req/day
  • order-service (critical) — 523K req/day
  • refund-worker (standard) — 12K req/day

Transitive impact: 12 services, 2.1M daily requests
Risk: HIGH — affects checkout flow
```

### Portfolio View

Aggregate health across all services from stored assessments.

```bash
$ nthlayer-observe portfolio --format table

Service            Availability    Latency    Status
─────────────────────────────────────────────────────
payment-api        73.2%           45.1%      WARNING
checkout-service   12.8%           89.3%      CRITICAL
user-service       95.4%           97.2%      HEALTHY
```

### Reliability Scorecard

Per-service reliability scores (0–100) with component breakdown.

```bash
$ nthlayer-observe scorecard --format json
```

---

## 🚀 Quick Start

```bash
# Install
pip install nthlayer-observe

# Collect error budgets from Prometheus
nthlayer-observe collect \
    --specs-dir path/to/manifests/ \
    --prometheus-url http://prometheus:9090

# Check if deployment is safe
nthlayer-observe check-deploy --service payment-api

# Detect budget drift
nthlayer-observe drift \
    --service payment-api \
    --prometheus-url http://prometheus:9090
```

---

## 🔄 CI/CD Integration

```yaml
# GitHub Actions — gate deployments on real data
- name: Check deployment readiness
  run: |
    nthlayer-observe collect \
      --specs-dir manifests/ \
      --prometheus-url ${{ secrets.PROMETHEUS_URL }}
    nthlayer-observe check-deploy --service ${{ matrix.service }}
```

Use [nthlayer](https://github.com/rsionnach/nthlayer) for build-time validation (SLO feasibility, policy checks). Use nthlayer-observe for runtime enforcement (error budgets, drift, deployment gates).

---

## Architecture

### Assessment Model

All commands produce **assessments** — structured records persisted to a SQLite store. The store is the integration point: `collect` writes assessments, `check-deploy` reads them, `portfolio`/`scorecard` aggregate them.

```
collect → SQLite assessment store ← check-deploy
                    ↑                ← portfolio
                    ↑                ← scorecard
                drift (direct Prometheus, writes assessment)
```

### Package Structure

```
src/nthlayer_observe/
├── cli.py            — 9 CLI subcommands
├── assessment.py     — Assessment dataclass + builder
├── config.py         — Configuration loader
├── sqlite_store.py   — SQLite assessment persistence
├── store.py          — Store protocol
├── slo/              — SLO collection + error budget calculation
├── drift/            — Drift analysis (linear regression)
├── gate/             — Deployment gate evaluation + correlation
├── verification/     — Metric existence verification
├── discovery/        — Prometheus metric discovery
├── dependencies/     — Dependency graph + blast radius
├── portfolio/        — Portfolio aggregation
├── deployments/      — Deployment event tracking
├── db/               — Database models
└── api/              — Future HTTP API
```

### What Moved Here

All runtime infrastructure from [nthlayer](https://github.com/rsionnach/nthlayer) during the Purify Generate epic:

- `slos/collector.py`, `storage.py`, `gates.py`, `correlator.py` → `slo/`, `gate/`
- `cli/deploy.py` → `cli.py::check-deploy`
- `drift/` → `drift/`
- `verification/` → `verification/`
- `portfolio/`, `scorecard/` → `portfolio/`
- `dependencies/` discovery providers → `dependencies/`
- `db/` → `db/`

nthlayer is now a pure compiler. nthlayer-observe is the runtime.

---

## OpenSRM Ecosystem

| Component | What it does | Link |
|-----------|-------------|------|
| **OpenSRM** | Specification for declaring service reliability requirements | [OpenSRM](https://github.com/rsionnach/opensrm) |
| **NthLayer** | Generate monitoring infrastructure from manifests | [nthlayer](https://github.com/rsionnach/nthlayer) |
| **nthlayer-observe** | Runtime enforcement: deployment gates, drift detection, error budgets (this repo) | [nthlayer-observe](https://github.com/rsionnach/nthlayer-observe) |
| **nthlayer-learn** | Data primitive for recording AI judgments and measuring correctness | [nthlayer-learn](https://github.com/rsionnach/nthlayer-learn) |
| **nthlayer-measure** | Quality measurement and governance for AI agents | [nthlayer-measure](https://github.com/rsionnach/nthlayer-measure) |
| **nthlayer-correlate** | Situational awareness through signal correlation | [nthlayer-correlate](https://github.com/rsionnach/nthlayer-correlate) |
| **nthlayer-respond** | Multi-agent incident response | [nthlayer-respond](https://github.com/rsionnach/nthlayer-respond) |

Each component works alone. nthlayer-observe needs only Prometheus and OpenSRM manifests.

---

## 🤝 Contributing

```bash
# Install uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/rsionnach/nthlayer-observe.git
cd nthlayer-observe
uv sync --extra dev
uv run pytest tests/ -v
```

---

## 📄 License

Apache 2.0
