"""Tests for nthlayer_observe.assessment module."""

from datetime import datetime, timezone

import pytest

from nthlayer_observe.assessment import (
    VALID_ASSESSMENT_TYPES,
    create,
    from_dict,
    to_dict,
)


class TestCreate:
    def test_generates_id_with_prefix(self):
        a = create("slo_state", "payment-api", {"current": 0.999})
        assert a.id.startswith("asm-")

    def test_generates_unique_ids(self):
        a1 = create("slo_state", "svc-a", {})
        a2 = create("slo_state", "svc-b", {})
        assert a1.id != a2.id

    def test_sequential_ids(self):
        a1 = create("slo_state", "svc-a", {})
        a2 = create("slo_state", "svc-b", {})
        seq1 = int(a1.id.rsplit("-", 1)[-1])
        seq2 = int(a2.id.rsplit("-", 1)[-1])
        assert seq2 > seq1

    def test_sets_timestamp_utc(self):
        a = create("drift", "checkout-svc", {"trend": "degrading"})
        assert a.timestamp.tzinfo is not None
        assert a.timestamp.tzinfo == timezone.utc

    def test_sets_default_producer(self):
        a = create("slo_state", "svc", {})
        assert a.producer == "nthlayer-observe"

    def test_custom_producer(self):
        a = create("slo_state", "svc", {}, producer="custom-tool")
        assert a.producer == "custom-tool"

    def test_sets_fields(self):
        data = {"slo_name": "availability", "current": 0.9987}
        a = create("slo_state", "payment-api", data)
        assert a.assessment_type == "slo_state"
        assert a.service == "payment-api"
        assert a.data == data

    def test_rejects_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid assessment_type"):
            create("invalid_type", "svc", {})

    def test_all_valid_types_accepted(self):
        for t in VALID_ASSESSMENT_TYPES:
            a = create(t, "svc", {})
            assert a.assessment_type == t


class TestSerialization:
    def test_to_dict_roundtrip(self):
        original = create("slo_state", "payment-api", {"current": 0.999})
        d = to_dict(original)
        restored = from_dict(d)
        assert restored.id == original.id
        assert restored.assessment_type == original.assessment_type
        assert restored.service == original.service
        assert restored.producer == original.producer
        assert restored.data == original.data

    def test_to_dict_timestamp_is_iso_string(self):
        a = create("drift", "svc", {})
        d = to_dict(a)
        assert isinstance(d["timestamp"], str)
        # Should parse back without error
        datetime.fromisoformat(d["timestamp"])

    def test_from_dict_parses_iso_timestamp(self):
        raw = {
            "id": "asm-2026-04-08-abcd1234-00001",
            "timestamp": "2026-04-08T12:00:00+00:00",
            "assessment_type": "gate",
            "service": "auth-service",
            "producer": "nthlayer-observe",
            "data": {"decision": "blocked"},
        }
        a = from_dict(raw)
        assert a.timestamp.tzinfo is not None
        assert a.timestamp.year == 2026

    def test_from_dict_accepts_datetime_object(self):
        ts = datetime.now(timezone.utc)
        raw = {
            "id": "asm-test",
            "timestamp": ts,
            "assessment_type": "slo_state",
            "service": "svc",
            "producer": "nthlayer-observe",
            "data": {},
        }
        a = from_dict(raw)
        assert a.timestamp == ts

    def test_data_preserved_through_roundtrip(self):
        nested_data = {
            "slo_name": "reversal_rate",
            "target": 0.015,
            "current": 0.027,
            "breaching": True,
            "details": {"window": "2m", "samples": 120},
        }
        original = create("slo_state", "fraud-detect", nested_data)
        restored = from_dict(to_dict(original))
        assert restored.data == nested_data
