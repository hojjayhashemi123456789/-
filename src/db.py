# -*- coding: utf-8 -*-
"""
مدیریت دیتابیس SQLite (consulting_bot.db) برای ذخیره لیست دانش‌آموزان،
شناسه عددی آن‌ها (برای جلوگیری از خطای محدودیت ۶۴ بایت callback_data در تلگرام)
و تاریخچه برنامه‌های صادرشده.
"""

from __future__ import annotations
import sqlite3
from pathlib import Path

DEFAULT_INITIAL_STUDENTS = [
    "امیرعلی ورمزیار",
    "محمد حسام",
    "سایه کرامت",
    "رضوانه",
    "هستی رضایی",
    "امیریاسین",
    "فاطمه برسرآمد",
    "علیرضا احمدی",
    "ایلین مهری",
    "غزال",
    "الهه برزکار",
    "امین جام",
    "ثنا",
    "ارمین",
    "ایلیا",
    "امیرمحمد",
    "هستی اصلی",
    "زهرا سرحدی",
]


class ConsultingDatabase:
    def __init__(self, db_path: str | Path = "consulting_bot.db", seed_defaults: bool = True) -> None:
        self.db_path = str(db_path)
        self._init_db(seed_defaults=seed_defaults)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self, seed_defaults: bool = True) -> None:
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
            if seed_defaults:
                cnt = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
                if cnt == 0:
                    for s_name in DEFAULT_INITIAL_STUDENTS:
                        conn.execute(
                            "INSERT OR IGNORE INTO students (name, usage_count) VALUES (?, 1)",
                            (s_name,),
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

    def list_students_with_ids(self, limit: int = 24) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name FROM students ORDER BY updated_at DESC, usage_count DESC, id ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [{"id": int(r["id"]), "name": str(r["name"])} for r in rows]

    def list_students(self, limit: int = 24) -> list[str]:
        return [item["name"] for item in self.list_students_with_ids(limit=limit)]

    def get_student_by_id(self, student_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            return str(row["name"]) if row else None

    def delete_student_by_id(self, student_id: int) -> str | None:
        name = self.get_student_by_id(student_id)
        if not name:
            return None
        with self._connect() as conn:
            conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
            conn.commit()
        return name

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

    def get_recent_plans(self, limit: int = 8) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT student_name, date_range, num_days, total_hours, created_at
                FROM generated_plans
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
