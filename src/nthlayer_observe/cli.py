"""CLI entry point for nthlayer-observe."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

from nthlayer_common.errors import main_with_error_handling


def _cmd_collect(args: argparse.Namespace) -> int:
    """Collect SLO metrics from Prometheus and store as assessments.

    Exit codes: 0 = all healthy, 2 = SLO breach detected (EXHAUSTED or CRITICAL).
    """
    from nthlayer_observe.slo.collector import SLOMetricCollector, results_to_assessments
    from nthlayer_observe.slo.spec_loader import SLODefinition, load_specs
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    definitions = load_specs(args.specs_dir)
    if not definitions:
        print("No SLO definitions found in specs directory", file=sys.stderr)
        return 0

    # Group SLOs by service
    by_service: dict[str, list[SLODefinition]] = defaultdict(list)
    for slo_def in definitions:
        by_service[slo_def.service].append(slo_def)

    collector = SLOMetricCollector(args.prometheus_url)

    async def _collect_all() -> list[tuple[str, list]]:
        """Collect all services in a single event loop."""
        all_results = []
        for service, slos in sorted(by_service.items()):
            results = await collector.collect(slos)
            all_results.append((service, results))
        return all_results

    all_results = asyncio.run(_collect_all())

    total_assessments = 0
    breach_count = 0

    with SQLiteAssessmentStore(args.store) as store:
        for service, results in all_results:
            assessments = results_to_assessments(results, service)

            for assessment in assessments:
                store.put(assessment)
                total_assessments += 1
                status = assessment.data.get("status", "")
                if status in ("EXHAUSTED", "CRITICAL"):
                    breach_count += 1

            budget = collector.calculate_aggregate_budget(results)
            print(
                f"{service}: {len(results)} SLOs, "
                f"{budget.consumed_percent:.1f}% consumed, "
                f"{budget.valid_slo_count} with data"
            )

    print(f"\n{total_assessments} assessments stored in {args.store}")

    if breach_count > 0:
        print(f"{breach_count} SLO(s) in EXHAUSTED or CRITICAL state", file=sys.stderr)
        return 2
    return 0


def _cmd_drift(args: argparse.Namespace) -> int:
    """Analyze SLO budget drift and store as assessments.

    Exit codes: 0 = NONE/INFO, 1 = WARN, 2 = CRITICAL.
    """
    import json

    from nthlayer_observe.assessment import create
    from nthlayer_observe.drift import DriftAnalysisError, DriftAnalyzer
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    analyzer = DriftAnalyzer(args.prometheus_url)

    try:
        result = asyncio.run(
            analyzer.analyze(
                service_name=args.service,
                tier=args.tier,
                slo=args.slo,
                window=args.window,
            )
        )
    except DriftAnalysisError as e:
        print(f"Drift analysis failed: {e}", file=sys.stderr)
        return 1

    assessment = create(
        "drift",
        args.service,
        {
            "slo_name": result.slo_name,
            "severity": result.severity.value,
            "pattern": result.pattern.value,
            "slope_per_week": result.metrics.slope_per_week,
            "days_until_exhaustion": result.projection.days_until_exhaustion,
            "current_budget": result.metrics.current_budget,
            "summary": result.summary,
            "recommendation": result.recommendation,
        },
    )

    with SQLiteAssessmentStore(args.store) as store:
        store.put(assessment)

    print(json.dumps(result.to_dict(), indent=2))
    return result.exit_code


def _cmd_verify(args: argparse.Namespace) -> int:
    """Verify declared metrics exist in Prometheus.

    Exit codes: 0 = all verified, 1 = optional missing, 2 = critical missing.
    """
    from nthlayer_observe.assessment import create
    from nthlayer_observe.slo.spec_loader import load_specs
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore
    from nthlayer_observe.verification.extractor import Resource, extract_metric_contract
    from nthlayer_observe.verification.verifier import MetricVerifier

    definitions = load_specs(args.specs_dir)
    if not definitions:
        print("No SLO definitions found in specs directory", file=sys.stderr)
        return 0

    # Build resources from spec definitions for the extractor
    by_service: dict[str, list[Resource]] = defaultdict(list)
    for slo_def in definitions:
        by_service[slo_def.service].append(
            Resource(kind="SLO", spec=slo_def.spec, name=slo_def.name)
        )

    verifier = MetricVerifier(args.prometheus_url)
    worst_exit = 0

    with SQLiteAssessmentStore(args.store) as store:
        for service, resources in sorted(by_service.items()):
            contract = extract_metric_contract(service, resources)
            if not contract.metrics:
                continue

            result = verifier.verify_contract(contract)

            assessment = create(
                "verification",
                service,
                {
                    "declared_metrics": len(contract.metrics),
                    "found_metrics": result.verified_count,
                    "missing_critical": [r.metric.name for r in result.missing_critical],
                    "missing_optional": [r.metric.name for r in result.missing_optional],
                    "exit_code": result.exit_code,
                },
            )
            store.put(assessment)

            status = "OK" if result.all_verified else "MISSING"
            print(
                f"{service}: {result.verified_count}/{len(contract.metrics)} metrics verified ({status})"
            )

            if result.exit_code > worst_exit:
                worst_exit = result.exit_code

    return worst_exit


def _cmd_discover(args: argparse.Namespace) -> int:
    """Discover available metrics from Prometheus."""
    import json

    from nthlayer_observe.discovery import MetricDiscoveryClient

    selector = f'{{service="{args.service}"}}' if args.service else "{}"
    client = MetricDiscoveryClient(args.prometheus_url)
    result = client.discover(selector)

    if args.output_format == "json":
        data = {
            "service": result.service,
            "total_metrics": result.total_metrics,
            "metrics": [
                {"name": m.name, "type": m.type.value, "technology": m.technology.value}
                for m in result.metrics
            ],
            "by_technology": {k: len(v) for k, v in result.metrics_by_technology.items()},
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Discovered {result.total_metrics} metrics for {result.service}")
        for tech, metrics in sorted(result.metrics_by_technology.items()):
            print(f"\n  {tech} ({len(metrics)} metrics):")
            for m in metrics[:5]:
                print(f"    {m.name} ({m.type.value})")
            if len(metrics) > 5:
                print(f"    ... and {len(metrics) - 5} more")

    return 0


def _cmd_dependencies(args: argparse.Namespace) -> int:
    """Discover service dependencies and store as assessments."""
    import json

    from nthlayer_observe.assessment import create
    from nthlayer_observe.dependencies import DependencyDiscovery
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    discovery = DependencyDiscovery()

    if args.prometheus_url:
        from nthlayer_observe.dependencies.providers.prometheus import PrometheusDepProvider

        discovery.add_provider(PrometheusDepProvider(url=args.prometheus_url))

    if not discovery.providers:
        print("No providers configured. Use --prometheus-url.", file=sys.stderr)
        return 1

    result = asyncio.run(discovery.discover(args.service))

    assessment = create(
        "dependency",
        args.service,
        {
            "dependencies_discovered": result.total_dependencies,
            "upstream": [
                {"service": d.target.canonical_name, "type": d.dep_type.value, "provider": d.providers[0] if d.providers else "unknown"}
                for d in result.upstream
            ],
            "downstream": [
                {"service": d.source.canonical_name, "type": d.dep_type.value, "provider": d.providers[0] if d.providers else "unknown"}
                for d in result.downstream
            ],
            "providers_queried": result.providers_queried,
            "errors": list(result.errors.values()),
        },
    )

    with SQLiteAssessmentStore(args.store) as store:
        store.put(assessment)

    print(json.dumps(assessment.data, indent=2))
    return 0


def _cmd_blast_radius(args: argparse.Namespace) -> int:
    """Analyze deployment blast radius."""
    import json

    from nthlayer_observe.dependencies import DependencyDiscovery, create_demo_discovery

    if args.prometheus_url:
        from nthlayer_observe.dependencies.providers.prometheus import PrometheusDepProvider

        discovery = DependencyDiscovery()
        discovery.add_provider(PrometheusDepProvider(url=args.prometheus_url))
        graph = asyncio.run(discovery.build_graph([args.service]))
    else:
        discovery, graph = create_demo_discovery()

    result = discovery.calculate_blast_radius(args.service, graph)

    data = {
        "service": result.service,
        "tier": result.tier,
        "risk_level": result.risk_level,
        "total_services_affected": result.total_services_affected,
        "critical_services_affected": result.critical_services_affected,
        "recommendation": result.recommendation,
    }
    print(json.dumps(data, indent=2))

    exit_codes = {"critical": 2, "high": 2, "medium": 1, "low": 0}
    return exit_codes.get(result.risk_level, 0)


def _cmd_check_deploy(args: argparse.Namespace) -> int:
    """Check if deployment should be allowed based on assessment data.

    Exit codes: 0 = APPROVED, 1 = WARNING, 2 = BLOCKED.
    """
    import json

    from nthlayer_observe.assessment import create
    from nthlayer_observe.gate.evaluator import check_deploy
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    with SQLiteAssessmentStore(args.store) as store:
        result = check_deploy(args.service, args.tier, store)

        # Store gate assessment
        assessment = create(
            "gate",
            args.service,
            {
                "action": "deploy",
                "decision": result.result.name.lower(),
                "budget_remaining_pct": result.budget_remaining_pct,
                "warning_threshold": result.warning_threshold,
                "blocking_threshold": result.blocking_threshold,
                "slo_count": result.slo_count,
                "reasons": [result.message] + result.recommendations,
            },
        )
        store.put(assessment)

    print(json.dumps({
        "service": result.service,
        "tier": result.tier,
        "decision": result.result.name,
        "budget_remaining_pct": round(result.budget_remaining_pct, 1),
        "message": result.message,
        "recommendations": result.recommendations,
    }, indent=2))

    exit_codes = {
        "APPROVED": 0,
        "WARNING": 1,
        "BLOCKED": 2,
    }
    return exit_codes.get(result.result.name, 0)


def _cmd_explain(args: argparse.Namespace) -> int:
    """Show human-readable budget explanations from assessment store."""
    import json

    from nthlayer_common.explanation import format_explanation
    from nthlayer_observe.explanation import ExplanationEngine
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore
    from nthlayer_observe.store import AssessmentFilter

    with SQLiteAssessmentStore(args.store) as store:
        engine = ExplanationEngine()

        if args.service:
            services = [args.service]
        else:
            all_assessments = store.query(
                AssessmentFilter(assessment_type="slo_state", limit=0)
            )
            services = sorted({a.service for a in all_assessments})

        if not services:
            print("No SLO assessments found in store.", file=sys.stderr)
            return 0

        all_explanations = []
        for service in services:
            explanations = engine.explain_service(
                service, store, slo_filter=args.slo
            )
            all_explanations.extend(explanations)

        if not all_explanations:
            print("No matching SLO assessments found.", file=sys.stderr)
            return 0

        fmt = args.output_format
        if fmt == "json":
            print(json.dumps(
                [e.to_dict() for e in all_explanations], indent=2
            ))
        else:
            for exp in all_explanations:
                print(format_explanation(exp, fmt=fmt))
                print()

    return 0


def _cmd_portfolio(args: argparse.Namespace) -> int:
    """Aggregate service health from assessment store."""
    import json

    from nthlayer_observe.portfolio import build_portfolio
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    with SQLiteAssessmentStore(args.store) as store:
        summary = build_portfolio(store)

    if not summary.services:
        print("No slo_state assessments found. Run 'collect' first.", file=sys.stderr)
        return 0

    if args.output_format == "json":
        data = {
            "total_services": summary.total_services,
            "healthy": summary.healthy_count,
            "warning": summary.warning_count,
            "critical": summary.critical_count,
            "exhausted": summary.exhausted_count,
            "services": [
                {
                    "service": svc.service,
                    "overall_status": svc.overall_status,
                    "slos": [
                        {"name": s.name, "status": s.status, "current_sli": s.current_sli, "percent_consumed": s.percent_consumed}
                        for s in svc.slos
                    ],
                }
                for svc in summary.services
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Portfolio: {summary.total_services} services")
        print(f"  Healthy: {summary.healthy_count}  Warning: {summary.warning_count}  Critical: {summary.critical_count}  Exhausted: {summary.exhausted_count}")
        for svc in summary.services:
            print(f"\n  {svc.service} ({svc.overall_status})")
            for s in svc.slos:
                sli = f"{s.current_sli:.2f}%" if s.current_sli is not None else "N/A"
                print(f"    {s.name}: {s.status} (SLI: {sli})")

    return 0


def _cmd_scorecard(args: argparse.Namespace) -> int:
    """Score service reliability from assessment store."""
    import json

    from nthlayer_observe.portfolio import build_portfolio, score_service
    from nthlayer_observe.sqlite_store import SQLiteAssessmentStore

    with SQLiteAssessmentStore(args.store) as store:
        summary = build_portfolio(store)

    if not summary.services:
        print("No slo_state assessments found. Run 'collect' first.", file=sys.stderr)
        return 0

    scored = [(svc, score_service(svc)) for svc in summary.services]
    scored.sort(key=lambda x: x[1], reverse=True)

    if args.output_format == "json":
        data = [
            {"service": svc.service, "score": round(score, 1), "status": svc.overall_status, "slo_count": len(svc.slos)}
            for svc, score in scored
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Scorecard: {len(scored)} services\n")
        for svc, score in scored:
            print(f"  {svc.service}: {score:.0f}/100 ({svc.overall_status}, {len(svc.slos)} SLOs)")

    return 0


@main_with_error_handling()
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nthlayer-observe",
        description="Deterministic runtime infrastructure — reads live system state, produces structured assessments.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    collect_parser = subparsers.add_parser(
        "collect", help="Collect SLO metrics and produce assessments"
    )
    collect_parser.add_argument(
        "--specs-dir", type=Path, required=True, help="Directory of OpenSRM spec YAMLs"
    )
    collect_parser.add_argument(
        "--prometheus-url", required=True, help="Prometheus server URL"
    )
    collect_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )

    drift_parser = subparsers.add_parser("drift", help="Detect SLO budget drift patterns")
    drift_parser.add_argument("--service", required=True, help="Service name")
    drift_parser.add_argument("--prometheus-url", required=True, help="Prometheus server URL")
    drift_parser.add_argument(
        "--tier", default="standard", choices=["critical", "standard", "low"],
        help="Service tier (default: standard)"
    )
    drift_parser.add_argument("--window", default=None, help="Analysis window (e.g., 30d)")
    drift_parser.add_argument("--slo", default="availability", help="SLO name (default: availability)")
    drift_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )

    verify_parser = subparsers.add_parser(
        "verify", help="Verify metric existence in Prometheus"
    )
    verify_parser.add_argument(
        "--specs-dir", type=Path, required=True, help="Directory of OpenSRM spec YAMLs"
    )
    verify_parser.add_argument(
        "--prometheus-url", required=True, help="Prometheus server URL"
    )
    verify_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )

    discover_parser = subparsers.add_parser("discover", help="Discover available metrics")
    discover_parser.add_argument("--prometheus-url", required=True, help="Prometheus server URL")
    discover_parser.add_argument("--service", default=None, help="Service name to filter by")
    discover_parser.add_argument(
        "--format", dest="output_format", default="table", choices=["table", "json"],
        help="Output format (default: table)"
    )

    deps_parser = subparsers.add_parser("dependencies", help="Discover service dependencies")
    deps_parser.add_argument("--service", required=True, help="Service name")
    deps_parser.add_argument("--prometheus-url", default=None, help="Prometheus server URL")
    deps_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )

    blast_parser = subparsers.add_parser("blast-radius", help="Analyze deployment blast radius")
    blast_parser.add_argument("--service", required=True, help="Service name")
    blast_parser.add_argument("--prometheus-url", default=None, help="Prometheus server URL")

    portfolio_parser = subparsers.add_parser(
        "portfolio", help="Aggregate service health from assessments"
    )
    portfolio_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )
    portfolio_parser.add_argument(
        "--format", dest="output_format", default="table", choices=["table", "json"],
        help="Output format (default: table)"
    )

    scorecard_parser = subparsers.add_parser(
        "scorecard", help="Score service reliability from assessments"
    )
    scorecard_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )
    scorecard_parser.add_argument(
        "--format", dest="output_format", default="table", choices=["table", "json"],
        help="Output format (default: table)"
    )

    check_deploy_parser = subparsers.add_parser(
        "check-deploy", help="Evaluate deployment gate from assessments"
    )
    check_deploy_parser.add_argument("--service", required=True, help="Service name")
    check_deploy_parser.add_argument(
        "--tier", default="standard", choices=["critical", "standard", "low"],
        help="Service tier (default: standard)"
    )
    check_deploy_parser.add_argument(
        "--store", default="assessments.db", help="Assessment store path (default: assessments.db)"
    )

    explain_parser = subparsers.add_parser(
        "explain", help="Show human-readable budget explanations"
    )
    explain_parser.add_argument(
        "--store", default="assessments.db",
        help="Assessment store path (default: assessments.db)",
    )
    explain_parser.add_argument("--service", help="Filter by service name")
    explain_parser.add_argument("--slo", help="Filter by SLO name")
    explain_parser.add_argument(
        "--format", dest="output_format", default="table",
        choices=["table", "json", "markdown"],
        help="Output format (default: table)",
    )

    args = parser.parse_args(argv)

    dispatch = {
        "collect": _cmd_collect,
        "drift": _cmd_drift,
        "verify": _cmd_verify,
        "discover": _cmd_discover,
        "dependencies": _cmd_dependencies,
        "blast-radius": _cmd_blast_radius,
        "portfolio": _cmd_portfolio,
        "scorecard": _cmd_scorecard,
        "check-deploy": _cmd_check_deploy,
        "explain": _cmd_explain,
    }

    handler = dispatch.get(args.command)
    if handler:
        return handler(args)

    return 0
