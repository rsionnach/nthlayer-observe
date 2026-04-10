"""Portfolio aggregation from assessment store."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from nthlayer_observe.store import AssessmentFilter, AssessmentStore

# Status severity order for worst-status calculation
_STATUS_SEVERITY = {
    "EXHAUSTED": 4,
    "CRITICAL": 3,
    "WARNING": 2,
    "ERROR": 1,
    "NO_DATA": 0,
    "HEALTHY": -1,
    "UNKNOWN": -2,
}


@dataclass
class SLOHealth:
    """Health of a single SLO from assessment data."""

    name: str
    status: str
    current_sli: float | None = None
    objective: float | None = None
    percent_consumed: float | None = None


@dataclass
class ServiceHealth:
    """Aggregated health for a service across all its SLOs."""

    service: str
    slos: list[SLOHealth] = field(default_factory=list)
    overall_status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if self.slos and self.overall_status == "UNKNOWN":
            self.overall_status = _worst_status([s.status for s in self.slos])


@dataclass
class PortfolioSummary:
    """Org-level portfolio health aggregated from assessments."""

    services: list[ServiceHealth] = field(default_factory=list)
    total_services: int = 0
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    exhausted_count: int = 0


def build_portfolio(store: AssessmentStore) -> PortfolioSummary:
    """Build portfolio summary from recent slo_state assessments.

    Reads the most recent slo_state assessment per service+SLO combination,
    groups by service, and aggregates health status.
    """
    assessments = store.query(
        AssessmentFilter(assessment_type="slo_state", limit=0)
    )

    # Group by service, keeping only the latest assessment per service+slo_name
    latest: dict[str, dict[str, dict]] = defaultdict(dict)
    for a in assessments:
        slo_name = a.data.get("slo_name", "unknown")
        key = slo_name
        # Assessments are ordered by timestamp desc, so first seen is latest
        if key not in latest[a.service]:
            latest[a.service][key] = a.data

    services = []
    for service_name in sorted(latest):
        slos = []
        for slo_name, data in sorted(latest[service_name].items()):
            slos.append(
                SLOHealth(
                    name=slo_name,
                    status=data.get("status", "UNKNOWN"),
                    current_sli=data.get("current_sli"),
                    objective=data.get("objective"),
                    percent_consumed=data.get("percent_consumed"),
                )
            )
        services.append(ServiceHealth(service=service_name, slos=slos))

    status_counts = defaultdict(int)
    for svc in services:
        bucket = _status_bucket(svc.overall_status)
        status_counts[bucket] += 1

    return PortfolioSummary(
        services=services,
        total_services=len(services),
        healthy_count=status_counts["healthy"],
        warning_count=status_counts["warning"],
        critical_count=status_counts["critical"],
        exhausted_count=status_counts["exhausted"],
    )


def _worst_status(statuses: list[str]) -> str:
    """Return the worst status from a list."""
    if not statuses:
        return "UNKNOWN"
    return max(statuses, key=lambda s: _STATUS_SEVERITY.get(s, -2))


def _status_bucket(status: str) -> str:
    """Map a status to a summary bucket.

    UNKNOWN/NO_DATA/ERROR are not counted in any severity bucket —
    they represent missing information, not active failures.
    """
    buckets = {
        "HEALTHY": "healthy",
        "WARNING": "warning",
        "CRITICAL": "critical",
        "EXHAUSTED": "exhausted",
        "UNKNOWN": "unknown",
        "NO_DATA": "unknown",
        "ERROR": "unknown",
    }
    return buckets.get(status, "unknown")
