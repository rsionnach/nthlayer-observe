"""SQLite-backed assessment store with WAL mode and thread-local connections."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from nthlayer_observe.assessment import Assessment, from_dict, to_dict
from nthlayer_observe.store import AssessmentFilter, AssessmentStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id               TEXT PRIMARY KEY,
    timestamp        TEXT NOT NULL,
    assessment_type  TEXT NOT NULL,
    service          TEXT NOT NULL,
    producer         TEXT NOT NULL,
    data             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assessments_timestamp ON assessments(timestamp);
CREATE INDEX IF NOT EXISTS idx_assessments_service ON assessments(service);
CREATE INDEX IF NOT EXISTS idx_assessments_type ON assessments(assessment_type);
CREATE INDEX IF NOT EXISTS idx_assessments_svc_type ON assessments(service, assessment_type);
"""


class SQLiteAssessmentStore(AssessmentStore):
    """SQLite-backed assessment store.

    Uses the same connection pattern as SQLiteVerdictStore:
    thread-local connections, WAL mode, 5s busy timeout.
    Can share the same database file as the verdict store.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _conn(self) -> sqlite3.Connection:
        """Return a thread-local connection with WAL mode enabled."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def put(self, assessment: Assessment) -> None:
        data = json.dumps(to_dict(assessment))
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO assessments
                   (id, timestamp, assessment_type, service, producer, data)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    assessment.id,
                    assessment.timestamp.isoformat(),
                    assessment.assessment_type,
                    assessment.service,
                    assessment.producer,
                    data,
                ),
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Assessment {assessment.id} already exists")
        conn.commit()

    def get(self, assessment_id: str) -> Assessment | None:
        row = self._conn().execute(
            "SELECT data FROM assessments WHERE id = ?",
            (assessment_id,),
        ).fetchone()
        if row is None:
            return None
        return from_dict(json.loads(row["data"]))

    def query(self, criteria: AssessmentFilter) -> list[Assessment]:
        clauses: list[str] = []
        params: list = []

        if criteria.service:
            clauses.append("service = ?")
            params.append(criteria.service)
        if criteria.assessment_type:
            clauses.append("assessment_type = ?")
            params.append(criteria.assessment_type)
        if criteria.producer:
            clauses.append("producer = ?")
            params.append(criteria.producer)
        if criteria.from_time:
            clauses.append("timestamp >= ?")
            params.append(criteria.from_time.isoformat())
        if criteria.to_time:
            clauses.append("timestamp <= ?")
            params.append(criteria.to_time.isoformat())

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT data FROM assessments {where} ORDER BY timestamp DESC"

        if criteria.limit > 0:
            sql += " LIMIT ?"
            params.append(criteria.limit)

        rows = self._conn().execute(sql, params).fetchall()
        return [from_dict(json.loads(row["data"])) for row in rows]

    def close(self) -> None:
        """Close the thread-local connection if open."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def __enter__(self) -> SQLiteAssessmentStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
