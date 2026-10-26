# -*- coding: utf-8 -*-
"""
مدیریت دیتابیس SQLite (consulting_bot.db) برای ذخیره لیست دانش‌آموزان،
شناسه عددی آن‌ها (برای جلوگیری از خطای محدودیت ۶۴ بایت callback_data در تلگرام)
و تاریخچه برنامه‌های صادرشده.
"""

from __future__ import annotations
import sqlite3
from pathlib import Path


class ConsultingDatabase:
    def __init__(self, db_path: str | Path = "consulting_bot.db") -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    usage_count INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL,
                    date_range TEXT NOT NULL,
                    num_days INTEGER NOT NULL,
                    total_hours REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def add_or_touch_student(self, name: str) -> None:
        clean = name.strip()
        if not clean:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO students (name, usage_count, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    usage_count = usage_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (clean,),
            )
            conn.commit()

    def list_students_with_ids(self, limit: int = 12) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name FROM students ORDER BY updated_at DESC, usage_count DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"id": int(r["id"]), "name": str(r["name"])} for r in rows]

    def list_students(self, limit: int = 12) -> list[str]:
        return [item["name"] for item in self.list_students_with_ids(limit=limit)]

    def get_student_by_id(self, student_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            return str(row["name"]) if row else None

    def delete_student(self, name: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM students WHERE name = ?", (name.strip(),))
            conn.commit()
            return cur.rowcount > 0

    def log_plan(
        self, student_name: str, date_range: str, num_days: int, total_hours: float
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generated_plans (student_name, date_range, num_days, total_hours)
                VALUES (?, ?, ?, ?)
                """,
                (student_name.strip(), date_range, num_days, total_hours),
            )
            conn.commit()
