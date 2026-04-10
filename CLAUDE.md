# nthlayer-observe

Deterministic runtime infrastructure layer for the NthLayer ecosystem. Reads live system state from Prometheus and produces structured assessments. No LLM calls — pure deterministic logic only.

<!-- AUTO-MANAGED: module-description -->
## Purpose

- Reads live Prometheus metrics and produces structured SLO assessments (stateful, deterministic, no LLM)
- CLI entrypoint: `nthlayer-observe` (also runnable as `python -m nthlayer_observe`)
- Runtime deps: `nthlayer-common` (local workspace), `structlog`, `pyyaml`, `scipy`, `numpy`
- Optional dep groups: `kubernetes` (`kubernetes>=28.0`), `zookeeper` (`kazoo>=2.9`), `etcd` (`etcd3>=0.12`), `service-discovery` (kazoo+etcd3)
- Dev deps: `nthlayer-learn` (local workspace, for shared-DB integration tests)
- CLI subcommands — all fully implemented:
  - `collect` — Collect SLO metrics from Prometheus and store assessments; exit 0 (all healthy) or exit 2 (EXHAUSTED/CRITICAL breach)
  - `drift` — Detect SLO budget drift patterns; exit 0 (NONE/INFO), 1 (WARN), 2 (CRITICAL)
  - `verify` — Verify declared metrics exist in Prometheus; exit 0 (all verified), 1 (optional missing), 2 (critical missing)
  - `discover` — Discover available metrics from Prometheus; groups by technology and type; exit 0
  - `dependencies` — Discover service dependencies via configured providers; stores "dependency" assessment; exit 0
  - `blast-radius` — Analyze deployment blast radius from dependency graph; exit 0 (low), 1 (medium), 2 (high/critical)
  - `portfolio` — Aggregate service health from slo_state assessments; table or JSON output; exit 0 (no-data prints stderr, still exits 0); args: `--store` (default: assessments.db), `--format` (table|json, default: table)
  - `scorecard` — Score service reliability (0–100) sorted descending; table or JSON output; exit 0; args: `--store` (default: assessments.db), `--format` (table|json, default: table)
  - `check-deploy` — Evaluate deployment gate based on slo_state assessments; exit 0 (APPROVED), 1 (WARNING), 2 (BLOCKED)
- `ObserveConfig` dataclass: `prometheus_url="http://localhost:9090"`, `store_path="assessments.db"`
<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: architecture -->
## Structure

```
pyproject.toml          # name=nthlayer-observe, version=0.1.0, entrypoint=nthlayer_observe.cli:main
src/nthlayer_observe/
    __init__.py         # public API: Assessment, AssessmentFilter, AssessmentStore, MemoryAssessmentStore, SQLiteAssessmentStore, VALID_ASSESSMENT_TYPES, create, from_dict, to_dict
    __main__.py         # python -m nthlayer_observe support
    assessment.py       # Assessment dataclass, VALID_ASSESSMENT_TYPES, create/to_dict/from_dict
    store.py            # AssessmentStore ABC, AssessmentFilter, MemoryAssessmentStore
    sqlite_store.py     # SQLiteAssessmentStore — WAL mode, thread-local connections, shared-DB capable
    cli.py              # main() — _cmd_collect(), _cmd_drift(), _cmd_verify(), _cmd_discover(), _cmd_dependencies(), _cmd_blast_radius(), _cmd_portfolio(), _cmd_scorecard(), _cmd_check_deploy() all implemented; @main_with_error_handling()
    config.py           # ObserveConfig dataclass (prometheus_url, store_path)
    api/                # (stub) Runtime HTTP API server
    db/                 # (stub) Runtime database layer
    dependencies/       # Dependency discovery orchestrator and providers (fully implemented)
        __init__.py     # exports: DependencyDiscovery, DependencyDiscoveryResult, DiscoveryError, create_demo_discovery, BaseDepProvider, ProviderHealth
        discovery.py    # DependencyDiscovery dataclass — add_provider(), set_tier(), health_check(), discover(service), build_graph(services), calculate_blast_radius(service, graph, max_depth=10); DependencyDiscoveryResult (service, upstream, downstream, providers_queried, errors); create_demo_discovery() → 8-service demo graph with 7 edges
        providers/
            __init__.py     # exports Backstage+Consul (always); Zookeeper+etcd (optional, graceful ImportError)
            base.py         # BaseDepProvider ABC: discover(), list_services(), health_check(), get_service_attributes(), discover_all(); ProviderHealth (healthy, message, latency_ms); helpers: deduplicate_dependencies(), infer_dependency_type()
            backstage.py    # BackstageDepProvider — /api/catalog/entities; spec.dependsOn (0.95) + spec.consumesApis (0.90); discover_downstream() via reverse scan; env: NTHLAYER_BACKSTAGE_URL, NTHLAYER_BACKSTAGE_TOKEN; httpx.AsyncClient
            consul.py       # ConsulDepProvider — catalog + health + Connect intentions (0.95) + service tags (0.80); env: NTHLAYER_CONSUL_URL, NTHLAYER_CONSUL_TOKEN; httpx.AsyncClient
            prometheus.py   # PrometheusDepProvider — DEPENDENCY_PATTERNS (http_client, grpc_client, database, redis, kafka, rabbitmq); async _query(); discover() + discover_downstream(); env: NTHLAYER_PROMETHEUS_URL, NTHLAYER_METRICS_USER/PASSWORD
            kubernetes.py   # KubernetesDepProvider — optional kubernetes package (lazy import); env: KUBECONFIG, NTHLAYER_K8S_NAMESPACE, NTHLAYER_K8S_CONTEXT; install: pip install nthlayer-observe[kubernetes]
            zookeeper.py    # ZookeeperDepProvider — optional kazoo; Curator-style discovery; env: NTHLAYER_ZOOKEEPER_HOSTS, NTHLAYER_ZOOKEEPER_ROOT; install: nthlayer-observe[service-discovery]
            etcd.py         # EtcdDepProvider — optional etcd3; service registration under prefix; JSON metadata with dep lists; env: NTHLAYER_ETCD_HOST, NTHLAYER_ETCD_PORT, NTHLAYER_ETCD_PREFIX; install: nthlayer-observe[service-discovery]
    deployments/        # (stub) Deployment event handling
    discovery/          # Metric and service discovery (fully implemented)
        __init__.py     # exports: MetricDiscoveryClient, MetricClassifier, DiscoveredMetric, DiscoveryResult, MetricType, TechnologyGroup
        models.py       # MetricType enum, TechnologyGroup enum, DiscoveredMetric/DiscoveryResult dataclasses (pure dataclasses, not pydantic)
        classifier.py   # MetricClassifier — classify() sets technology via prefix patterns, infers type from name suffix; does NOT override known type
        client.py       # MetricDiscoveryClient — sync httpx; discover(selector) → DiscoveryResult; queries /api/v1/series + /api/v1/metadata; fallback to /metrics endpoint; populates metrics_by_technology and metrics_by_type
    drift/              # SLO budget drift detection (fully implemented)
        __init__.py     # exports: DriftAnalyzer, DriftAnalysisError, DriftResult, DriftMetrics, DriftProjection, DriftSeverity, DriftPattern, PatternDetector, DRIFT_DEFAULTS, get_drift_defaults
        analyzer.py     # DriftAnalyzer — async analyze(), linear regression via scipy, exhaustion projection, severity classification; DriftAnalysisError
        models.py       # DriftSeverity/DriftPattern enums, DriftMetrics/DriftProjection/DriftResult dataclasses, DRIFT_DEFAULTS (by tier), get_drift_defaults()
        patterns.py     # PatternDetector — detect() classifies step-change/volatile/gradual/stable; detect_seasonal() via day-of-week variance
    gate/               # Deployment gate evaluation (fully implemented)
        __init__.py     # exports: ConditionEvaluator, CorrelationInput, CorrelationResult, EvaluationResult, GateCheckResult, PolicyContext, check_deploy, correlate, get_current_context, is_business_hours, is_freeze_period, is_peak_traffic, is_weekday
        conditions.py   # Pure condition functions (no external data access): get_current_context(), is_business_hours(start_hour=9, end_hour=17), is_weekday(), is_freeze_period(start_date, end_date), is_peak_traffic(peak_hours=[(10,12),(14,16)])
        correlator.py   # 5-factor weighted deployment correlator; CorrelationInput/CorrelationResult dataclasses; correlate(inp) → CorrelationResult; thresholds: HIGH=0.7, MEDIUM=0.5, LOW=0.3, BLOCKING=0.8; weights: burn_rate=0.35, proximity=0.25, magnitude=0.15, dependency=0.15, history=0.10
        evaluator.py    # check_deploy(service, tier, store, policy=None) → GateCheckResult; reads slo_state assessments; applies tier thresholds from nthlayer_common.tiers.TIER_CONFIGS; GateCheckResult (service, tier, result, budget_remaining_pct, warning_threshold, blocking_threshold, message, recommendations, slo_count)
        policies.py     # PolicyContext dataclass (budget_remaining, budget_consumed, burn_rate, tier, environment, service, team, downstream_count, high_criticality_downstream, now); ConditionEvaluator (DSL: AND/OR/NOT, parentheses, comparisons ==!=>=<=><, function calls); EvaluationResult; evaluate_all() returns most restrictive match by blocking value
    portfolio/          # Portfolio health aggregation (fully implemented)
        __init__.py     # exports: PortfolioSummary, SLOHealth, ServiceHealth, build_portfolio, score_service
        aggregator.py   # build_portfolio(store) → PortfolioSummary; SLOHealth (name, status, current_sli, objective, percent_consumed); ServiceHealth (service, slos, overall_status; __post_init__ computes worst status); PortfolioSummary (services, total_services, healthy_count, warning_count, critical_count, exhausted_count); status severity order: EXHAUSTED=4, CRITICAL=3, WARNING=2, ERROR=1, NO_DATA=0, HEALTHY=-1, UNKNOWN=-2; queries all slo_state assessments (limit=0), keeps first-seen per service+slo_name (query returns desc so first=latest)
        scorer.py       # score_service(health: ServiceHealth) → float; (healthy_slo_count / total_slos) * 100; returns 0.0 for empty SLO list
    slo/                # SLO state collection and storage
        __init__.py     # exports: BudgetSummary, SLODefinition, SLOMetricCollector, SLOResult, load_specs, results_to_assessments
        collector.py    # SLOMetricCollector, SLOResult, BudgetSummary, results_to_assessments
        spec_loader.py  # SLODefinition, load_specs
    verification/       # Metric existence verification (fully implemented)
        __init__.py     # exports: ContractVerificationResult, DeclaredMetric, MetricContract, MetricSource, MetricVerifier, Resource, VerificationResult, extract_metric_contract
        models.py       # MetricSource enum, DeclaredMetric/MetricContract/VerificationResult/ContractVerificationResult dataclasses
        extractor.py    # Resource dataclass, extract_metric_contract(), _extract_metrics_from_query() with _PROMQL_KEYWORDS frozenset
        verifier.py     # MetricVerifier — sync httpx, verify_contract(), verify_metric(), _check_metric_exists() (tries with service label then without), _query_series() via /api/v1/series, test_connection()
        exporter_guidance.py  # ExporterInfo dataclass, EXPORTERS dict (8 exporters), detect_missing_exporters(), get_exporter_guidance(), format_exporter_guidance()
tests/
    test_cli.py              # TestCLI (help/no-args/collect-requires-args/drift-requires-args/verify-requires-args/discover-requires-args/dependencies-requires-args/blast-radius-requires-args/check-deploy-requires-args), TestPackage (version/config/common)
    test_dependencies.py     # TestBaseProviderHelpers (infer_dependency_type/deduplicate), TestDependencyDiscoveryResult, TestDependencyDiscovery (empty/provider/error/health/blast-radius), TestCreateDemoDiscovery (8 services/7 edges), TestDependenciesCLI (dependencies+blast-radius --help)
    test_discovery.py        # TestModels (4 cases), TestMetricClassifier (9 cases: pg/redis/http/kube/custom/counter/histogram/gauge/no-override), TestMetricDiscoveryClient (6 cases: init/auth/bearer/service-extraction/mocked-discover/connection-error), TestDiscoverCLI (discover --help)
    test_assessment.py       # TestCreate, TestSerialization — Assessment dataclass and serialization
    test_store.py            # TestStorePutAndGet, TestStoreQuery, TestGetLatest, TestStoreSharedDb — parametrized over Memory+SQLite
    test_sqlite_concurrency.py  # TestConcurrentAccess — 5-thread concurrent writes, WAL mode assertion
    test_collect_cli.py      # TestCollectCLI — collect help, missing args, empty specs dir
    test_slo_collector.py    # TestSLOMetricCollector, TestCalculateAggregateBudget, TestHelpers, TestResultsToAssessments
    test_slo_spec_loader.py  # TestLoadSpecs (10 cases), TestSLODefinition
    test_drift.py            # TestDriftModels (models/serialization), TestPatternDetector (7 pattern cases), TestDriftAnalyzer (thresholds/projection/severity/summary/async-mock), TestDriftCLI (drift --help)
    test_verification.py     # TestMetricExtraction (6 cases), TestExtractMetricContract (5 cases), TestVerificationResult (3 cases), TestContractVerificationResult (4 cases), TestMetricVerifier (5 cases), TestExporterGuidance (7 cases)
    test_portfolio.py        # TestBuildPortfolio (7 cases: empty store/single healthy/multiple services/worst-SLO status/exhausted/dedup-by-latest/alphabetical sort), TestServiceHealth (2 cases: post_init computes worst/empty stays UNKNOWN), TestScorer (4 cases: all-healthy=100/mixed=50/no-slos=0/all-critical=0), TestPortfolioCLI (portfolio --help + scorecard --help)
    test_gate_correlator.py  # TestBurnRateScore (5), TestProximityScore (2), TestMagnitudeScore (4), TestDependencyScore (5), TestHistoryScore (4), TestCorrelate (5: high-confidence/low-confidence/result-fields/confidence-labels/threshold-constants)
    test_gate_evaluator.py   # TestCheckDeploy (11: approved/warning/blocked/no-assessments/multi-slo/custom-policy-warning/custom-policy-blocking/low-tier-advisory/exhaustion-freeze/exhaustion-require-approval/slo-without-percent_consumed-ignored), TestCheckDeployCLI (check-deploy --help)
    test_gate_policies.py    # TestConditions (10), TestPolicyContext (2), TestConditionEvaluator (19: empty/simple/equality/inequality/AND/OR/NOT/parentheses/bool-var/missing-var/numeric/function-business_hours/weekday/freeze_period/invalid-fails-safe/evaluate_all-most-restrictive/evaluate_all-no-match/float/double-quotes/complex)
```
<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: build-commands -->
## Commands

```bash
# Run tests
uv run pytest tests/ -v --tb=short -x

# Lint
uv run ruff check src/ tests/ --ignore E501
```
<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: conventions -->
## Conventions

- **Deterministic only** — no LLM calls, no probabilistic logic; all assessments are rule-based from live metrics
- **Stateful** — unlike `nthlayer` (pure stateless compiler), this component maintains assessment state in SQLite (`assessments.db`)
- **Error handling** — CLI `main()` uses `@main_with_error_handling()` from `nthlayer_common.errors`; `collect` exits 2 on breach, 0 on healthy; `drift` exits 0 (NONE/INFO), 1 (WARN), 2 (CRITICAL); `verify` exits 0 (all verified), 1 (optional missing), 2 (critical missing); `blast-radius` exits 0 (low), 1 (medium), 2 (high/critical); `check-deploy` exits 0 (APPROVED), 1 (WARNING), 2 (BLOCKED)
- **Config** — `ObserveConfig` dataclass with sensible defaults; Prometheus URL and store path are the two primary runtime knobs
- **Imports** — `nthlayer-common` is a local workspace dep (`../nthlayer-common`), `nthlayer-learn` is a dev-only dep (`../nthlayer-learn/lib/python`); both resolved via `[tool.uv.sources]`
- **Tests** — assert on exit codes and structured output, never on raw text in captured stdout; stderr substring assertions only for `"not yet implemented"` (stub) and `"No SLO definitions found"` (collect empty-dir)
- **Lookup dicts over regex** — `_determine_status()` and `_parse_window_minutes()` use lookup dicts, not regex; exception: `extractor.py` uses regex for PromQL metric name extraction (necessary — PromQL grammar cannot be parsed with lookup dicts)
- **Async Prometheus queries** — `SLOMetricCollector.collect()` is async; `_cmd_collect()` wraps with `asyncio.run()`; provider closed in `finally` block
- **Sync Prometheus verification** — `MetricVerifier` uses sync `httpx.Client` (not async); verification is a one-shot series query per metric, no concurrency needed
- **Sync Prometheus discovery** — `MetricDiscoveryClient` uses sync `httpx.get()` (not async); discovery queries /api/v1/series + /api/v1/metadata per metric; classifier runs post-fetch; no concurrency needed
- **Async dependency discovery** — `DependencyDiscovery.discover()` fans out upstream+downstream queries to all providers in parallel via `asyncio.gather`; provider errors are captured per-provider in `result.errors`, never raised; `_cmd_dependencies()` wraps with `asyncio.run()`
- **Optional provider imports** — Kubernetes, Zookeeper, and etcd providers use lazy/guarded imports; missing optional package raises a clear error at call time, not at import time; `providers/__init__.py` silently sets provider classes to `None` on `ImportError`
- **Dependency deduplication** — `DiscoveredDependency`: keeps highest confidence per source:target:type key; `ResolvedDependency`: merges providers list (set union) and takes max confidence

## Data Model

- **Assessment** — deterministic observation of system state; NOT a verdict (no confidence, no LLM reasoning)
  - Fields: `id`, `timestamp` (UTC datetime), `assessment_type`, `service`, `producer`, `data` (dict)
  - `VALID_ASSESSMENT_TYPES`: `"slo_state"`, `"drift"`, `"verification"`, `"gate"`, `"dependency"`
  - ID format: `asm-{YYYY-MM-DD}-{uuid8}-{seq:05d}` — globally sortable, thread-safe sequential counter
  - `create()` raises `ValueError` on invalid `assessment_type`; default producer is `"nthlayer-observe"`

## Storage

- **AssessmentStore** — ABC with `put()`, `get()`, `query()`, `get_latest()`; `put()` raises `ValueError` on duplicate ID
- **AssessmentFilter** — dataclass: `service`, `assessment_type`, `producer`, `from_time`, `to_time`, `limit=100` (0=unlimited); `query()` returns results ordered by timestamp descending
- **MemoryAssessmentStore** — thread-safe in-memory store; use in tests
- **SQLiteAssessmentStore** — thread-local connections, WAL mode, 5s busy timeout; 4 indexes (timestamp, service, assessment_type, svc+type composite); context manager support
- **Shared DB** — `SQLiteAssessmentStore` and `SQLiteVerdictStore` (nthlayer-learn) can share the same SQLite file via independent tables; `assessments` and `verdicts` tables do not conflict

## SLO Collection

- **SLODefinition** — dataclass: `service`, `name`, `spec` (raw dict with target/window/indicator)
- **load_specs(specs_dir)** — reads `.yaml`/`.yml` files; accepts `apiVersion: srm/v1` or `opensrm/v1`; silently skips non-SRM files, malformed YAML, missing `metadata.name`, non-dict slos; raises `ValueError` for nonexistent directory
- **SLOMetricCollector** — stateless async collector; reads `PROMETHEUS_USERNAME`/`PROMETHEUS_PASSWORD` or `NTHLAYER_METRICS_USER`/`NTHLAYER_METRICS_PASSWORD` env vars
- **SLOResult** — dataclass per SLO: `name`, `objective`, `window`, `total_budget_minutes`, `current_sli`, `burned_minutes`, `percent_consumed`, `status`, `error`
- **Status thresholds** — `percent_consumed >= 100` → `EXHAUSTED`; `>= 80` → `CRITICAL`; `>= 50` → `WARNING`; else `HEALTHY`; `NO_DATA` when SLI=0 or no query; `ERROR` on Prometheus failure
- **Query building** — uses `indicator.query` directly, or builds from `indicators[0].success_ratio.{good_query,total_query}`; substitutes `${service}`/`$service` with service name; latency SLOs return `NO_DATA`
- **Spec compatibility** — `target` field (OpenSRM) takes precedence over `objective` field (legacy nthlayer)
- **results_to_assessments()** — converts `list[SLOResult]` → `list[Assessment]` with `assessment_type="slo_state"`
- **BudgetSummary** — aggregate across all valid SLOs: `total_budget_minutes`, `burned_budget_minutes`, `remaining_percent`, `consumed_percent`, `valid_slo_count`

## Drift Detection

- **DriftAnalyzer** — async `analyze(service_name, tier, slo, window)` queries `slo:error_budget_remaining:ratio{service="...", slo="..."}` (Prometheus range query), calculates trend via `scipy.stats.linregress`, projects exhaustion, classifies severity
- **DriftResult.to_dict()** — serializes to JSON for CLI stdout output
- **DriftSeverity** — `NONE | INFO | WARN | CRITICAL`; exit codes: NONE→0, INFO→0, WARN→1, CRITICAL→2
- **DriftPattern** — `STABLE | GRADUAL_DECLINE | GRADUAL_IMPROVEMENT | STEP_CHANGE_DOWN | STEP_CHANGE_UP | SEASONAL | VOLATILE`; `STEP_CHANGE_DOWN` always maps to `CRITICAL` severity
- **PatternDetector.detect()** — priority order: step change (within 36h window, threshold 0.05) → volatile (low r² + high variance) → gradual/stable by weekly slope significance
- **DRIFT_DEFAULTS** — per-tier config; `critical`: warn=-0.2%/week, critical=-0.5%/week, exhaustion_warn=30d, exhaustion_critical=14d; `standard`: warn=-0.5%/week, critical=-1.0%/week, exhaustion_warn=14d, exhaustion_critical=7d; `low`: warn=-1.0%/week, critical=-2.0%/week, exhaustion_warn=7d, exhaustion_critical=3d
- **CLI `drift` args** — `--service` (required), `--prometheus-url` (required), `--tier` (default: standard, choices: critical/standard/low), `--slo` (default: availability), `--window` (optional, e.g. 30d), `--store` (default: assessments.db)
- **Assessment storage** — `_cmd_drift()` stores a `"drift"` assessment via `SQLiteAssessmentStore` in addition to printing JSON

## Metric Discovery

- **MetricDiscoveryClient** — sync httpx; `discover(selector)` fetches metric names via `/api/v1/series`, metadata (type/help) via `/api/v1/metadata`, label values via second `/api/v1/series` query; fallback `_get_metrics_from_endpoint()` parses raw `/metrics` text for non-Prometheus targets (triggered when URL contains `/metrics` or `fly.dev`)
- **DiscoveryResult** — `service`, `total_metrics`, `metrics: list[DiscoveredMetric]`, `metrics_by_technology: dict[str, list[DiscoveredMetric]]`, `metrics_by_type: dict[str, list[DiscoveredMetric]]`
- **DiscoveredMetric** — `name`, `type: MetricType`, `technology: TechnologyGroup`, `help_text: str | None`, `labels: dict[str, list[str]]`
- **MetricClassifier** — `classify(metric)` sets technology from `TECHNOLOGY_PATTERNS` (regex prefix/substring matching); infers type from `TYPE_PATTERNS` only when `metric.type == MetricType.UNKNOWN`; default technology → `CUSTOM`; default inferred type → `GAUGE`
- **TechnologyGroup** — 10 values: `POSTGRESQL | REDIS | MONGODB | KAFKA | MYSQL | RABBITMQ | KUBERNETES | HTTP | CUSTOM | UNKNOWN`
- **MetricType** — 5 values: `COUNTER | GAUGE | HISTOGRAM | SUMMARY | UNKNOWN`
- **CLI `discover` args** — `--prometheus-url` (required), `--service` (optional, adds `{service="..."}` selector), `--format` (table|json, default: table); table output groups by technology (up to 5 metrics shown per group, "... and N more" for overflow); JSON output includes name/type/technology per metric + `by_technology` counts
- **Auth** — `MetricDiscoveryClient` accepts `username`/`password` (Basic auth) or `bearer_token` (Authorization header); reads no env vars directly (caller responsibility)

## Metric Verification

- **MetricContract** — the contract for a service: `service_name`, `metrics: list[DeclaredMetric]`; properties `critical_metrics`, `optional_metrics`, `unique_metric_names`
- **DeclaredMetric** — a metric declared in spec: `name`, `source: MetricSource`, `query`, `resource_name`; `is_critical` = True for `SLO_INDICATOR` or `ALERT` sources
- **MetricSource** — enum: `SLO_INDICATOR | OBSERVABILITY | ALERT`
- **ContractVerificationResult** — aggregate result: `all_verified`, `critical_verified`, `missing_critical`, `missing_optional`, `verified_count`, `exit_code` (0/1/2)
- **MetricVerifier** — sync httpx; `verify_contract(contract)` checks all metrics; `_check_metric_exists()` first tries `{metric}{service="..."}` selector, then bare metric name; reads `PROMETHEUS_USERNAME`/`PROMETHEUS_PASSWORD` env vars
- **extract_metric_contract(service, resources)** — builds `MetricContract` from `list[Resource]`; handles `SLO` kind (extracts from `indicators[].success_ratio.{total,good,error}_query` and `latency_query`) and `Observability` kind (extracts from `spec.metrics[]`); deduplicates by name (first occurrence wins)
- **_extract_metrics_from_query(query)** — regex-based PromQL parser; filters `_PROMQL_KEYWORDS` frozenset (40+ PromQL functions/operators) and `__`-prefixed internal labels
- **ExporterGuidance** — `EXPORTERS` dict maps 8 exporter types (postgresql, redis, elasticsearch, mongodb, mysql, kafka, rabbitmq, nginx) to helm install commands and docs URLs; `detect_missing_exporters()` matches metric prefixes to exporter types; `format_exporter_guidance()` produces helm install instructions
- **CLI `verify` args** — `--specs-dir` (required), `--prometheus-url` (required), `--store` (default: assessments.db)
- **Assessment storage** — `_cmd_verify()` stores a `"verification"` assessment per service via `SQLiteAssessmentStore`

## Dependency Discovery

- **DependencyDiscovery** — dataclass orchestrator; holds `providers: list[BaseDepProvider]`, `resolver: IdentityResolver`, `tier_mapping: dict[str, str]`; `discover(service)` returns `DependencyDiscoveryResult` with upstream + downstream `ResolvedDependency` lists; `build_graph(services)` returns `DependencyGraph`
- **DependencyDiscoveryResult** — `service`, `upstream: list[ResolvedDependency]`, `downstream: list[ResolvedDependency]`, `providers_queried: list[str]`, `errors: dict[str, str]`, `total_dependencies` property
- **BaseDepProvider** — ABC: `name` (property), `discover(service)`, `list_services()`, `health_check()`, `get_service_attributes(service)`, `discover_all()` (async generator)
- **ProviderHealth** — dataclass: `healthy: bool`, `message: str`, `latency_ms: float | None`
- **calculate_blast_radius(service, graph, max_depth=10)** — risk levels: critical (critical_affected>=2 or total>=10), high (total>=6 or critical>=2), medium (total>=3 or critical>=1), low (otherwise); returns `BlastRadiusResult` from `nthlayer_common.dependency_models`
- **Providers:**
  - `PrometheusDepProvider` — discovers from HTTP/gRPC/DB/Redis/Kafka/RabbitMQ metric label patterns; `--prometheus-url` optional (falls back to demo data in blast-radius)
  - `BackstageDepProvider` — `spec.dependsOn` (0.95) + `spec.consumesApis` (0.90); supports downstream reverse scan; env: `NTHLAYER_BACKSTAGE_URL`, `NTHLAYER_BACKSTAGE_TOKEN`
  - `ConsulDepProvider` — catalog + Connect intentions (0.95) + tags (0.80); env: `NTHLAYER_CONSUL_URL`, `NTHLAYER_CONSUL_TOKEN`
  - `KubernetesDepProvider` — optional `kubernetes>=28.0`; install: `nthlayer-observe[kubernetes]`; env: `KUBECONFIG`, `NTHLAYER_K8S_NAMESPACE`, `NTHLAYER_K8S_CONTEXT`
  - `ZookeeperDepProvider` — optional `kazoo>=2.9`; install: `nthlayer-observe[service-discovery]`; env: `NTHLAYER_ZOOKEEPER_HOSTS`, `NTHLAYER_ZOOKEEPER_ROOT`
  - `EtcdDepProvider` — optional `etcd3>=0.12`; install: `nthlayer-observe[service-discovery]`; env: `NTHLAYER_ETCD_HOST`, `NTHLAYER_ETCD_PORT`, `NTHLAYER_ETCD_PREFIX`
- **CLI `dependencies` args** — `--service` (required), `--prometheus-url` (optional), `--store` (default: assessments.db); stores `"dependency"` assessment; prints JSON of upstream/downstream lists
- **CLI `blast-radius` args** — `--service` (required), `--prometheus-url` (optional, uses demo data if absent); JSON output: service/tier/risk_level/total_services_affected/critical_services_affected/recommendation
- **create_demo_discovery()** — returns `(DependencyDiscovery, DependencyGraph)` with 8 pre-wired services (payment-api, user-service, checkout-api, order-service, mobile-gateway, notification-service, postgresql, redis) and 7 edges; tier_mapping sets payment-api/checkout-api/order-service as critical

## Deployment Gate

- **check_deploy(service, tier, store, policy=None)** — reads recent `slo_state` assessments for the service; keeps latest per SLO name (query returns desc); averages `percent_consumed` across all SLOs; applies thresholds
- **Decision logic** — no assessments → APPROVED (default); `budget_remaining <= 0` + `freeze_deploys` policy → BLOCKED; `budget_remaining <= 0` + `require_approval` policy → WARNING; `budget_remaining <= blocking_threshold` → BLOCKED; `budget_remaining <= warning_threshold` → WARNING; else → APPROVED
- **GateCheckResult** — fields: `service`, `tier`, `result (GateResult)`, `budget_remaining_pct`, `warning_threshold`, `blocking_threshold`, `message`, `recommendations: list[str]`, `slo_count`
- **THRESHOLDS** — derived from `nthlayer_common.tiers.TIER_CONFIGS`; `critical`: warning=20%, blocking=10%; `standard`: warning=20%, blocking=None (advisory only, max WARNING); `low`: warning=20%, blocking=None
- **GatePolicy** — from `nthlayer_common.gate_models`; overrides tier defaults: `warning`, `blocking`, `on_exhausted` (list: `"freeze_deploys"` → BLOCKED, `"require_approval"` → WARNING)
- **Assessment storage** — `_cmd_check_deploy()` stores a `"gate"` assessment with action/decision/budget_remaining_pct/warning_threshold/blocking_threshold/slo_count/reasons
- **CLI `check-deploy` args** — `--service` (required), `--tier` (default: standard, choices: critical/standard/low), `--store` (default: assessments.db); JSON output: service/tier/decision/budget_remaining_pct/message/recommendations
- **CorrelationInput** — pre-computed inputs: `deployment_id`, `service`, `deploy_time`, `burn_detected_at` (datetime: when burn was first detected, used for proximity scoring), `burn_rate_before`, `burn_rate_after`, `burn_minutes`, `is_same_service`, `is_direct_upstream`, `is_transitive_upstream`, `is_yaml_downstream`, `recent_deploy_count`, `prior_correlations`
- **correlate(inp)** — 5-factor weighted scoring; no async, no DB queries; weights: burn_rate=0.35, proximity=0.25, magnitude=0.15, dependency=0.15, history=0.10
- **Factor scoring** — burn_rate: spike ratio (5x=1.0, no baseline→absolute/0.1); proximity: exponential decay half-life ~30min; magnitude: 10+ min=1.0; dependency: same/direct=1.0, yaml_downstream=0.6, transitive=0.4, none=0.0; history: prior_correlations/recent_deploy_count (capped 1.0)
- **CorrelationResult.confidence_label** — HIGH (>=0.7), MEDIUM (>=0.5), LOW (>=0.3), NONE (<0.3); BLOCKING threshold=0.8
- **ConditionEvaluator** — evaluates DSL condition strings against a context dict; supports: AND/OR/NOT, parentheses, comparisons (==, !=, >=, <=, >, <), string literals (single or double quotes), boolean literals, function calls
- **ConditionEvaluator.FUNCTIONS** — `business_hours()`, `weekday()`, `freeze_period(start, end)`, `peak_traffic()`; functions use `PolicyContext.now` when available, else `datetime.now()`
- **evaluate_all(conditions)** — returns `(matched: bool, most_restrictive: dict | None)`; picks condition with highest `blocking` value among all matching `when` clauses; fails safe on invalid condition (returns False)
<!-- END AUTO-MANAGED -->
