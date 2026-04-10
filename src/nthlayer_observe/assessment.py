"""Assessment dataclass — a deterministic observation of system state."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

VALID_ASSESSMENT_TYPES = frozenset({
    "slo_state",
    "drift",
    "verification",
    "gate",
    "dependency",
})

_id_lock = threading.Lock()
_id_sequence = 0


def _generate_id() -> str:
    """Generate a unique assessment ID. Thread-safe."""
    global _id_sequence
    with _id_lock:
        _id_sequence += 1
        seq = _id_sequence
    short_uuid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m-%d")
    return f"asm-{date_part}-{short_uuid}-{seq:05d}"


@dataclass
class Assessment:
    """A deterministic observation of system state.

    NOT a verdict. No judgment, no confidence score, no LLM reasoning.
    Same inputs always produce the same assessment.
    """

    id: str
    timestamp: datetime
    assessment_type: str
    service: str
    producer: str
    data: dict


def create(
    assessment_type: str,
    service: str,
    data: dict,
    *,
    producer: str = "nthlayer-observe",
) -> Assessment:
    """Create a new Assessment with generated ID and UTC timestamp."""
    if assessment_type not in VALID_ASSESSMENT_TYPES:
        raise ValueError(
            f"Invalid assessment_type {assessment_type!r}, "
            f"must be one of {sorted(VALID_ASSESSMENT_TYPES)}"
        )
    return Assessment(
        id=_generate_id(),
        timestamp=datetime.now(timezone.utc),
        assessment_type=assessment_type,
        service=service,
        producer=producer,
        data=data,
    )


def to_dict(assessment: Assessment) -> dict:
    """Serialize an Assessment to a plain dict."""
    return {
        "id": assessment.id,
        "timestamp": assessment.timestamp.isoformat(),
        "assessment_type": assessment.assessment_type,
        "service": assessment.service,
        "producer": assessment.producer,
        "data": assessment.data,
    }


def from_dict(raw: dict) -> Assessment:
    """Deserialize an Assessment from a plain dict."""
    ts = raw["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return Assessment(
        id=raw["id"],
        timestamp=ts,
        assessment_type=raw["assessment_type"],
        service=raw["service"],
        producer=raw["producer"],
        data=raw["data"],
    )
