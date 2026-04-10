"""Load OpenSRM specs from a directory and extract SLO definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SLODefinition:
    """A single SLO extracted from an OpenSRM spec."""

    service: str
    name: str
    spec: dict[str, Any]  # raw SLO spec: target, window, indicator, etc.


VALID_API_VERSIONS = frozenset({"opensrm/v1", "srm/v1"})


def load_specs(specs_dir: str | Path) -> list[SLODefinition]:
    """Load OpenSRM specs from a directory and extract SLO definitions.

    Reads all .yaml/.yml files, skips non-SRM files silently.
    Returns a flat list of SLODefinition across all specs.
    """
    specs_path = Path(specs_dir)
    if not specs_path.is_dir():
        raise ValueError(f"Specs directory does not exist: {specs_dir}")

    definitions: list[SLODefinition] = []

    for path in sorted(specs_path.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError):
            continue

        if not isinstance(data, dict):
            continue

        api_version = data.get("apiVersion")
        if api_version not in VALID_API_VERSIONS:
            continue

        metadata = data.get("metadata", {})
        service = metadata.get("name")
        if not service:
            continue

        spec = data.get("spec", {})
        slos = spec.get("slos", {})
        if not isinstance(slos, dict):
            continue

        for slo_name, slo_spec in slos.items():
            if not isinstance(slo_spec, dict):
                continue
            definitions.append(
                SLODefinition(service=service, name=slo_name, spec=slo_spec)
            )

    return definitions
