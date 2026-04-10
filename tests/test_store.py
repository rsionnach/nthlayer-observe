"""Tests for assessment store implementations."""

from datetime import datetime, timedelta, timezone

import pytest

from nthlayer_learn import SQLiteVerdictStore
from nthlayer_learn.core import create as create_verdict

from nthlayer_observe.assessment import create
from nthlayer_observe.sqlite_store import SQLiteAssessmentStore
from nthlayer_observe.store import AssessmentFilter, MemoryAssessmentStore


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryAssessmentStore()
    return SQLiteAssessmentStore(tmp_path / "test.db")


class TestStorePutAndGet:
    def test_put_and_get(self, store):
        a = create("slo_state", "payment-api", {"current": 0.999})
        store.put(a)
        retrieved = store.get(a.id)
        assert retrieved is not None
        assert retrieved.id == a.id
        assert retrieved.service == "payment-api"
        assert retrieved.data == {"current": 0.999}

    def test_get_missing_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_duplicate_put_raises(self, store):
        a = create("slo_state", "svc", {})
        store.put(a)
        with pytest.raises(ValueError, match="already exists"):
            store.put(a)


class TestStoreQuery:
    def test_query_by_service(self, store):
        store.put(create("slo_state", "svc-a", {}))
        store.put(create("slo_state", "svc-b", {}))
        results = store.query(AssessmentFilter(service="svc-a"))
        assert len(results) == 1
        assert results[0].service == "svc-a"

    def test_query_by_assessment_type(self, store):
        store.put(create("slo_state", "svc", {}))
        store.put(create("drift", "svc", {}))
        results = store.query(AssessmentFilter(assessment_type="drift"))
        assert len(results) == 1
        assert results[0].assessment_type == "drift"

    def test_query_by_producer(self, store):
        store.put(create("slo_state", "svc", {}, producer="tool-a"))
        store.put(create("slo_state", "svc", {}, producer="tool-b"))
        results = store.query(AssessmentFilter(producer="tool-a"))
        assert len(results) == 1
        assert results[0].producer == "tool-a"

    def test_query_combined_filters(self, store):
        store.put(create("slo_state", "svc-a", {}))
        store.put(create("drift", "svc-a", {}))
        store.put(create("slo_state", "svc-b", {}))
        results = store.query(
            AssessmentFilter(service="svc-a", assessment_type="slo_state")
        )
        assert len(results) == 1

    def test_query_respects_limit(self, store):
        for _ in range(5):
            store.put(create("slo_state", "svc", {}))
        results = store.query(AssessmentFilter(limit=3))
        assert len(results) == 3

    def test_query_limit_zero_returns_all(self, store):
        for _ in range(5):
            store.put(create("slo_state", "svc", {}))
        results = store.query(AssessmentFilter(limit=0))
        assert len(results) == 5

    def test_query_ordered_by_timestamp_desc(self, store):
        a1 = create("slo_state", "svc", {})
        a2 = create("slo_state", "svc", {})
        store.put(a1)
        store.put(a2)
        results = store.query(AssessmentFilter())
        assert results[0].timestamp >= results[1].timestamp

    def test_query_by_time_range(self, store):
        now = datetime.now(timezone.utc)
        old = create("slo_state", "svc", {})
        # Manually set timestamp to 2 hours ago
        from nthlayer_observe.assessment import Assessment

        old_assessment = Assessment(
            id=old.id,
            timestamp=now - timedelta(hours=2),
            assessment_type="slo_state",
            service="svc",
            producer="nthlayer-observe",
            data={},
        )
        store.put(old_assessment)
        store.put(create("slo_state", "svc", {}))

        cutoff = now - timedelta(hours=1)
        results = store.query(AssessmentFilter(from_time=cutoff))
        assert len(results) == 1
        assert results[0].timestamp >= cutoff

    def test_query_empty_store(self, store):
        results = store.query(AssessmentFilter())
        assert results == []


class TestGetLatest:
    def test_returns_most_recent(self, store):
        store.put(create("slo_state", "svc", {"v": 1}))
        store.put(create("slo_state", "svc", {"v": 2}))
        latest = store.get_latest("svc", "slo_state")
        assert latest is not None
        assert latest.data["v"] == 2

    def test_filters_by_type(self, store):
        store.put(create("slo_state", "svc", {"type": "slo"}))
        store.put(create("drift", "svc", {"type": "drift"}))
        latest = store.get_latest("svc", "drift")
        assert latest is not None
        assert latest.data["type"] == "drift"

    def test_returns_none_when_empty(self, store):
        assert store.get_latest("svc", "slo_state") is None

    def test_returns_none_when_no_match(self, store):
        store.put(create("slo_state", "svc-a", {}))
        assert store.get_latest("svc-b", "slo_state") is None


class TestStoreSharedDb:
    """Prove assessments and verdicts coexist in one SQLite database."""

    def test_both_stores_work_on_same_file(self, tmp_path):
        db_path = tmp_path / "shared.db"

        # Create both stores pointing at the same file
        assessment_store = SQLiteAssessmentStore(db_path)
        verdict_store = SQLiteVerdictStore(db_path)

        # Write an assessment
        assessment = create("slo_state", "payment-api", {"current": 0.9987})
        assessment_store.put(assessment)

        # Write a verdict using nthlayer-learn's dict-based API
        verdict = create_verdict(
            subject={"type": "evaluation", "ref": "payment-api", "summary": "Test evaluation"},
            judgment={"action": "approve", "confidence": 0.95},
            producer={"system": "nthlayer-measure"},
        )
        verdict_store.put(verdict)

        # Both are independently retrievable
        retrieved_assessment = assessment_store.get(assessment.id)
        assert retrieved_assessment is not None
        assert retrieved_assessment.service == "payment-api"
        assert retrieved_assessment.data == {"current": 0.9987}

        retrieved_verdict = verdict_store.get(verdict.id)
        assert retrieved_verdict is not None
        assert retrieved_verdict.subject.ref == "payment-api"

    def test_tables_are_independent(self, tmp_path):
        db_path = tmp_path / "shared.db"

        assessment_store = SQLiteAssessmentStore(db_path)
        verdict_store = SQLiteVerdictStore(db_path)

        # Put 3 assessments
        for i in range(3):
            assessment_store.put(create("slo_state", f"svc-{i}", {}))

        # Put 2 verdicts
        for i in range(2):
            verdict_store.put(
                create_verdict(
                    subject={"type": "evaluation", "ref": f"svc-{i}", "summary": f"Test {i}"},
                    judgment={"action": "approve", "confidence": 0.9},
                    producer={"system": "nthlayer-measure"},
                )
            )

        # Counts are independent
        from nthlayer_learn.store import VerdictFilter

        assessments = assessment_store.query(AssessmentFilter())
        verdicts = verdict_store.query(VerdictFilter())
        assert len(assessments) == 3
        assert len(verdicts) == 2

    def test_shared_db_wal_mode(self, tmp_path):
        db_path = tmp_path / "shared.db"

        assessment_store = SQLiteAssessmentStore(db_path)
        SQLiteVerdictStore(db_path)

        # Both should use WAL mode on the same file
        conn = assessment_store._conn()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
