"""Tests for nthlayer_observe.slo.spec_loader module."""

import pytest
import yaml

from nthlayer_observe.slo.spec_loader import SLODefinition, load_specs


class TestLoadSpecs:
    def test_loads_slos_from_valid_spec(self, tmp_path):
        spec = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "payment-api"},
            "spec": {
                "slos": {
                    "availability": {"target": 99.95, "window": "30d"},
                    "latency": {"target": 200, "window": "30d", "unit": "ms"},
                }
            },
        }
        (tmp_path / "payment.yaml").write_text(yaml.dump(spec))

        definitions = load_specs(tmp_path)
        assert len(definitions) == 2
        assert definitions[0].service == "payment-api"
        assert definitions[0].name == "availability"
        assert definitions[0].spec["target"] == 99.95
        assert definitions[1].name == "latency"

    def test_loads_opensrm_v1_api_version(self, tmp_path):
        spec = {
            "apiVersion": "opensrm/v1",
            "metadata": {"name": "svc"},
            "spec": {"slos": {"avail": {"target": 99.9, "window": "7d"}}},
        }
        (tmp_path / "svc.yaml").write_text(yaml.dump(spec))

        definitions = load_specs(tmp_path)
        assert len(definitions) == 1

    def test_skips_non_srm_files(self, tmp_path):
        (tmp_path / "prometheus.yaml").write_text(
            yaml.dump({"global": {"scrape_interval": "15s"}})
        )
        (tmp_path / "valid.yaml").write_text(
            yaml.dump(
                {
                    "apiVersion": "srm/v1",
                    "metadata": {"name": "svc"},
                    "spec": {"slos": {"avail": {"target": 99.9, "window": "7d"}}},
                }
            )
        )
        definitions = load_specs(tmp_path)
        assert len(definitions) == 1
        assert definitions[0].service == "svc"

    def test_skips_non_yaml_files(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Specs")
        (tmp_path / "data.json").write_text("{}")
        definitions = load_specs(tmp_path)
        assert definitions == []

    def test_empty_directory(self, tmp_path):
        definitions = load_specs(tmp_path)
        assert definitions == []

    def test_nonexistent_directory_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            load_specs("/nonexistent/path")

    def test_skips_malformed_yaml(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("{{invalid yaml:")
        definitions = load_specs(tmp_path)
        assert definitions == []

    def test_skips_spec_without_metadata_name(self, tmp_path):
        spec = {
            "apiVersion": "srm/v1",
            "metadata": {},
            "spec": {"slos": {"avail": {"target": 99.9}}},
        }
        (tmp_path / "no-name.yaml").write_text(yaml.dump(spec))
        definitions = load_specs(tmp_path)
        assert definitions == []

    def test_skips_spec_without_slos(self, tmp_path):
        spec = {
            "apiVersion": "srm/v1",
            "metadata": {"name": "svc"},
            "spec": {"type": "api"},
        }
        (tmp_path / "no-slos.yaml").write_text(yaml.dump(spec))
        definitions = load_specs(tmp_path)
        assert definitions == []

    def test_multiple_specs_multiple_services(self, tmp_path):
        for name in ("svc-a", "svc-b"):
            spec = {
                "apiVersion": "srm/v1",
                "metadata": {"name": name},
                "spec": {"slos": {"avail": {"target": 99.9, "window": "30d"}}},
            }
            (tmp_path / f"{name}.yaml").write_text(yaml.dump(spec))

        definitions = load_specs(tmp_path)
        assert len(definitions) == 2
        services = {d.service for d in definitions}
        assert services == {"svc-a", "svc-b"}


class TestSLODefinition:
    def test_fields(self):
        d = SLODefinition(service="svc", name="avail", spec={"target": 99.9})
        assert d.service == "svc"
        assert d.name == "avail"
        assert d.spec["target"] == 99.9
