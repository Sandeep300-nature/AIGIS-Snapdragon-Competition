import time
import threading
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional

from .reminder_manager import ReminderManager
from .priority_engine import PriorityEngine, PriorityClass
from .reminder_conversation_manager import ReminderConversationManager

class ReminderScheduler:
    """
    Reminder Scheduler:
    Single Responsibility: Monitors current system time every 1 second (minimal CPU).
    Determines WHEN reminders become active and triggers milestone notifications.
    Does NOT decide HOW reminders are delivered.
    """

    def __init__(self, reminder_manager: ReminderManager, interval_seconds: float = 1.0):
        self.manager = reminder_manager
        self.interval = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.notification_callbacks: List[Callable[[List[Dict[str, Any]]], None]] = []
        # In-memory tracking of milestone notifications per reminder ID to prevent duplicates
        self.milestone_history: Dict[str, List[int]] = {}

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"[REMINDER SCHEDULER] 1-Second Lightweight Scheduler Started (Interval: {self.interval}s)")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def register_callback(self, callback: Callable[[List[Dict[str, Any]]], None]):
        self.notification_callbacks.append(callback)

    def _run_loop(self):
        while self.running:
            try:
                self._check_reminders_tick()
            except Exception as e:
                print(f"[REMINDER SCHEDULER] Tick error: {e}")
            
            time.sleep(self.interval)

    def _check_reminders_tick(self):
        all_reminders = self.manager.get_all_reminders()
        now = datetime.now()
        active_triggers = []

        for r in all_reminders:
            if r.completed or r.status in ["completed", "dismissed"]:
                continue

            try:
                r_dt = datetime.fromisoformat(r.datetime)
            except Exception:
                continue

            seconds_remaining = (r_dt - now).total_seconds()
            p_class = PriorityEngine.resolve_priority_class(r.title, r.type, r.priority)

            # Initialize milestone history for reminder if missing
            if r.id not in self.milestone_history:
                self.milestone_history[r.id] = []

            history = self.milestone_history[r.id]
            milestone = PriorityEngine.get_active_milestone(p_class, seconds_remaining, history)

            if milestone is not None:
                history.append(milestone)
                mode = ReminderConversationManager.determine_presentation_mode(p_class, is_speaking=False, seconds_remaining=seconds_remaining)
                phrase = ReminderConversationManager.generate_polite_interruption_phrase(r.title, milestone, p_class)

                if milestone == 0:
                    r.status = "due" if seconds_remaining >= -300 else "overdue"
                    r.last_notified = now.isoformat()
                    self.manager.storage.save_reminder(r)

                    # Structured High-Visibility Terminal Banner Output as requested
                    print("\n" + "=" * 40)
                    print("REMINDER DUE")
                    print(f"Time     : {now.strftime('%H:%M:%S')}")
                    print(f"Title    : {r.title}")
                    print(f"Priority : {p_class.value.capitalize()}")
                    print("Status   : Notification Sent")
                    print("=" * 40 + "\n")

                trigger_item = r.to_dict()
                trigger_item["priority_class"] = p_class.value
                trigger_item["milestone_seconds"] = milestone
                trigger_item["presentation_mode"] = mode
                trigger_item["interruption_phrase"] = phrase
                active_triggers.append(trigger_item)

        if active_triggers:
            for cb in self.notification_callbacks:
                try:
                    cb(active_triggers)
                except Exception as e:
                    print(f"[REMINDER SCHEDULER] Callback error: {e}")
