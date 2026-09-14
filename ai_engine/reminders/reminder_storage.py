import os
import sqlite3
import json
from typing import List, Optional, Dict, Any
from .reminder_model import Reminder

class ReminderStorage:
    def __init__(self, db_path: str = ""):
        if not db_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "reminders.db")
        
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    type TEXT NOT NULL,
                    datetime TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    completed INTEGER NOT NULL,
                    last_notified TEXT
                )
            """)
            conn.commit()

    def save_reminder(self, reminder: Reminder) -> Reminder:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO reminders (
                    id, title, description, type, datetime, created_at, status, priority, completed, last_notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reminder.id,
                reminder.title,
                reminder.description,
                reminder.type,
                reminder.datetime,
                reminder.created_at,
                reminder.status,
                reminder.priority,
                1 if reminder.completed else 0,
                reminder.last_notified
            ))
            conn.commit()
        return reminder

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_reminder(row)
        return None

    def get_all_reminders(self) -> List[Reminder]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders ORDER BY datetime ASC")
            rows = cursor.fetchall()
            return [self._row_to_reminder(row) for row in rows]

    def delete_reminder(self, reminder_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_all(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders")
            conn.commit()

    def _row_to_reminder(self, row: sqlite3.Row) -> Reminder:
        return Reminder(
            reminder_id=row["id"],
            title=row["title"],
            description=row["description"],
            reminder_type=row["type"],
            datetime_str=row["datetime"],
            created_at=row["created_at"],
            status=row["status"],
            priority=row["priority"],
            completed=bool(row["completed"]),
            last_notified=row["last_notified"]
        )
