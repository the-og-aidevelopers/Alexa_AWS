"""SQLite storage for one household schedule and today's dose log."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (household_id, name)
);

CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id INTEGER NOT NULL DEFAULT 1,
    person_name TEXT NOT NULL,
    dose_label TEXT NOT NULL,
    time_local TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dose_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    logged_at TEXT NOT NULL,
    UNIQUE (schedule_id, day)
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.household_id = 1
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def scoped(self, household_id: int) -> "Store":
        scoped = object.__new__(Store)
        scoped.path = self.path
        scoped.household_id = household_id
        return scoped

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def seed_if_empty(self) -> None:
        if self.list_schedules() or self.list_people():
            return
        self.add_person("Mom")
        self.add_schedule("Mom", "lisinopril", "08:00")
        self.add_schedule("Mom", "lisinopril", "20:00")

    def add_person(self, name: str, household_id: int | None = None) -> dict[str, Any]:
        household_id = self.household_id if household_id is None else household_id
        cleaned = " ".join(name.split())
        existing = self.find_person(cleaned, household_id)
        if existing:
            return {"name": existing, "created": False}
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO people (household_id, name, created_at) VALUES (?, ?, ?)",
                (household_id, cleaned, created_at),
            )
        return {"name": cleaned, "created": True}

    def find_person(self, name: str, household_id: int | None = None) -> str | None:
        household_id = self.household_id if household_id is None else household_id
        needle = " ".join(name.split()).lower()
        for known in self.list_people(household_id):
            if known.lower() == needle:
                return known
        return None

    def list_people(self, household_id: int | None = None) -> list[str]:
        household_id = self.household_id if household_id is None else household_id
        with self.connect() as conn:
            registered = conn.execute(
                "SELECT name FROM people WHERE household_id = ? ORDER BY name",
                (household_id,),
            ).fetchall()
            scheduled = conn.execute(
                "SELECT DISTINCT person_name FROM schedules WHERE household_id = ?",
                (household_id,),
            ).fetchall()
        names: dict[str, str] = {}
        for row in registered:
            names[row["name"].lower()] = row["name"]
        for row in scheduled:
            names.setdefault(row["person_name"].lower(), row["person_name"])
        return [names[key] for key in sorted(names)]

    def list_schedules(self, household_id: int | None = None) -> list[dict[str, Any]]:
        household_id = self.household_id if household_id is None else household_id
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, household_id, person_name, dose_label, time_local
                FROM schedules
                WHERE household_id = ?
                ORDER BY time_local, person_name, dose_label, id
                """,
                (household_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_schedule(
        self,
        person_name: str,
        dose_label: str,
        time_local: str,
        household_id: int | None = None,
    ) -> dict[str, Any]:
        household_id = self.household_id if household_id is None else household_id
        self.add_person(person_name, household_id)
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedules (household_id, person_name, dose_label, time_local, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (household_id, person_name.strip(), dose_label.strip(), time_local, created_at),
            )
            schedule_id = int(cursor.lastrowid)
        return {
            "id": schedule_id,
            "household_id": household_id,
            "person_name": person_name.strip(),
            "dose_label": dose_label.strip(),
            "time_local": time_local,
        }

    def delete_schedule(self, schedule_id: int) -> bool:
        with self.connect() as conn:
            conn.execute("DELETE FROM dose_logs WHERE schedule_id IN (SELECT id FROM schedules WHERE id = ? AND household_id = ?)", (schedule_id, self.household_id))
            cursor = conn.execute("DELETE FROM schedules WHERE id = ? AND household_id = ?", (schedule_id, self.household_id))
            return cursor.rowcount > 0

    def get_log(self, schedule_id: int, day: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT schedule_id, day, status, reason, logged_at
                FROM dose_logs
                WHERE schedule_id = ? AND day = ?
                  AND schedule_id IN (SELECT id FROM schedules WHERE household_id = ?)
                """,
                (schedule_id, day, self.household_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_log(
        self,
        schedule_id: int,
        day: str,
        status: str,
        reason: str,
        logged_at: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dose_logs (schedule_id, day, status, reason, logged_at)
                SELECT ?, ?, ?, ?, ?
                WHERE EXISTS (SELECT 1 FROM schedules WHERE id = ? AND household_id = ?)
                ON CONFLICT (schedule_id, day) DO UPDATE SET
                    status = excluded.status,
                    reason = excluded.reason,
                    logged_at = excluded.logged_at
                """,
                (schedule_id, day, status, reason, logged_at, schedule_id, self.household_id),
            )

    def clear_logs(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM dose_logs WHERE schedule_id IN (SELECT id FROM schedules WHERE household_id = ?)", (self.household_id,))

