import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .reminder_model import Reminder
from .reminder_storage import ReminderStorage
from .reminder_parser import ReminderParser

class ReminderManager:
    def __init__(self, db_path: str = ""):
        self.storage = ReminderStorage(db_path=db_path)
        self.active_notifications: List[Dict[str, Any]] = []

    def create_reminder_from_text(self, text: str) -> Reminder:
        parsed = ReminderParser.parse_reminder_request(text)
        reminder = Reminder(
            title=parsed["title"],
            description=parsed["description"],
            reminder_type=parsed["type"],
            datetime_str=parsed["datetime"],
            priority=parsed["priority"]
        )
        return self.storage.save_reminder(reminder)

    def create_reminder_dict(self, data: Dict[str, Any]) -> Reminder:
        reminder = Reminder.from_dict(data)
        return self.storage.save_reminder(reminder)

    def get_all_reminders(self) -> List[Reminder]:
        return self.storage.get_all_reminders()

    def get_filtered_reminders(self, timeframe: Optional[str] = None, status: Optional[str] = None) -> List[Reminder]:
        reminders = self.storage.get_all_reminders()
        now = datetime.now()

        filtered = []
        for r in reminders:
            try:
                r_dt = datetime.fromisoformat(r.datetime)
            except Exception:
                continue

            if status and r.status.lower() != status.lower():
                continue

            if timeframe == "today":
                if r_dt.date() == now.date():
                    filtered.append(r)
            elif timeframe == "week":
                if now.date() <= r_dt.date() <= (now.date() + timedelta(days=7)):
                    filtered.append(r)
            elif timeframe == "overdue":
                if r_dt < now and not r.completed and r.status != "dismissed":
                    filtered.append(r)
            elif timeframe == "pending":
                if not r.completed and r.status != "dismissed":
                    filtered.append(r)
            else:
                filtered.append(r)

        return filtered

    def execute_action(self, reminder_id: str, action: str, new_datetime: Optional[str] = None) -> Optional[Reminder]:
        reminder = self.storage.get_reminder(reminder_id)
        if not reminder:
            return None

        now_str = datetime.now().isoformat()
        act = action.lower().strip()

        if act in ["complete", "done", "mark_done"]:
            reminder.completed = True
            reminder.status = "completed"
        elif act == "snooze":
            # Snooze +15 minutes
            r_dt = datetime.now() + timedelta(minutes=15)
            reminder.datetime = r_dt.strftime("%Y-%m-%dT%H:%M:%S")
            reminder.status = "snoozed"
            reminder.completed = False
        elif act == "reschedule" and new_datetime:
            reminder.datetime = new_datetime
            reminder.status = "pending"
            reminder.completed = False
        elif act == "dismiss":
            reminder.status = "dismissed"
            reminder.last_notified = now_str

        return self.storage.save_reminder(reminder)

    def delete_reminder(self, reminder_id: str) -> bool:
        return self.storage.delete_reminder(reminder_id)

    def check_startup_summary(self) -> Dict[str, Any]:
        """
        Runs on AIGIS startup: Loads reminders, compares current system time,
        and generates due & overdue summary messages.
        """
        all_reminders = self.storage.get_all_reminders()
        now = datetime.now()

        today_reminders = []
        overdue_reminders = []
        upcoming_10m = []

        for r in all_reminders:
            if r.completed or r.status in ["dismissed", "completed"]:
                continue
            try:
                r_dt = datetime.fromisoformat(r.datetime)
            except Exception:
                continue

            sec_rem = (r_dt - now).total_seconds()
            if r_dt < now:
                r.status = "overdue"
                self.storage.save_reminder(r)
                overdue_reminders.append(r)
            elif 0 <= sec_rem <= 600:
                upcoming_10m.append(r)
            elif r_dt.date() == now.date():
                today_reminders.append(r)

        summary_lines = []
        if upcoming_10m:
            summary_lines.append(f"Upcoming Urgent Notice: You have {len(upcoming_10m)} item(s) starting within the next 10 minutes:")
            for r in upcoming_10m:
                try:
                    time_str = datetime.fromisoformat(r.datetime).strftime("%I:%M %p")
                except Exception:
                    time_str = r.datetime
                summary_lines.append(f"- {r.title} at {time_str} ({r.type.upper()})")

        if today_reminders:
            if summary_lines:
                summary_lines.append("")
            summary_lines.append(f"Good day, sir. You have {len(today_reminders)} scheduled item(s) today:")
            for r in today_reminders:
                try:
                    time_str = datetime.fromisoformat(r.datetime).strftime("%I:%M %p")
                except Exception:
                    time_str = r.datetime
                summary_lines.append(f"- {r.title} at {time_str} ({r.type})")

        if overdue_reminders:
            if summary_lines:
                summary_lines.append("")
            summary_lines.append(f"Notice: You have {len(overdue_reminders)} overdue item(s):")
            for r in overdue_reminders:
                try:
                    time_str = datetime.fromisoformat(r.datetime).strftime("%b %d at %I:%M %p")
                except Exception:
                    time_str = r.datetime
                summary_lines.append(f"- {r.title} (scheduled {time_str})")

        return {
            "has_startup_items": bool(today_reminders or overdue_reminders or upcoming_10m),
            "today_count": len(today_reminders),
            "upcoming_count": len(upcoming_10m),
            "overdue_count": len(overdue_reminders),
            "summary_text": "\n".join(summary_lines) if summary_lines else "No pending reminders for today, sir.",
            "today_reminders": [r.to_dict() for r in today_reminders],
            "upcoming_reminders": [r.to_dict() for r in upcoming_10m],
            "overdue_reminders": [r.to_dict() for r in overdue_reminders]
        }

    def check_due_notifications(self) -> List[Dict[str, Any]]:
        """
        Background loop check (called every 30s): Finds pending reminders whose datetime <= now.
        Returns list of newly triggered notification objects.
        """
        all_reminders = self.storage.get_all_reminders()
        now = datetime.now()
        due_list = []

        for r in all_reminders:
            if r.completed or r.status in ["dismissed", "completed"]:
                continue
            try:
                r_dt = datetime.fromisoformat(r.datetime)
            except Exception:
                continue

            # Check if reminder is due (datetime <= now) and hasn't been completed/dismissed
            if r_dt <= now:
                r.status = "due" if abs((now - r_dt).total_seconds()) < 300 else "overdue"
                if not r.last_notified:
                    r.last_notified = now.isoformat()
                    self.storage.save_reminder(r)
                due_list.append(r.to_dict())

        return due_list
