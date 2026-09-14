from enum import Enum
from typing import List, Dict, Any, Optional

class PriorityClass(Enum):
    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"

class PriorityEngine:
    """
    Priority Engine:
    Single Responsibility: Decides IMPORTANCE & MILESTONE SCHEDULE for reminders.
    Supports four priority classes: CRITICAL, IMPORTANT, URGENT, ROUTINE.
    """

    CRITICAL_KEYWORDS = ["meeting", "interview", "medication", "medicine", "doctor", "emergency", "flight", "board", "critical", "urgent"]
    IMPORTANT_KEYWORDS = ["appointment", "bill", "rent", "assignment", "due", "project", "exam", "deadline"]
    URGENT_KEYWORDS = ["water", "stretch", "drink", "walk", "break", "small task", "call"]

    # Notification Milestone offsets in seconds before due time
    MILESTONES = {
        PriorityClass.CRITICAL: [600, 300, 60, 30, 0],   # 10m, 5m, 1m, 30s, 0s
        PriorityClass.IMPORTANT: [300, 30, 0],           # 5m, 30s, 0s
        PriorityClass.URGENT: [30, 0],                   # 30s, 0s
        PriorityClass.ROUTINE: [0]                       # 0s (Due time only)
    }

    @classmethod
    def resolve_priority_class(cls, title: str, category_type: str, explicit_priority: str = "normal") -> PriorityClass:
        text = f"{title} {category_type}".lower()
        p = explicit_priority.lower().strip()

        if p in ["high", "critical", "urgent"] or any(k in text for k in cls.CRITICAL_KEYWORDS):
            return PriorityClass.CRITICAL
        elif any(k in text for k in cls.IMPORTANT_KEYWORDS):
            return PriorityClass.IMPORTANT
        elif any(k in text for k in cls.URGENT_KEYWORDS):
            return PriorityClass.URGENT
        else:
            return PriorityClass.ROUTINE

    @classmethod
    def get_active_milestone(cls, priority_class: PriorityClass, seconds_remaining: float, notified_milestones: List[int]) -> Optional[int]:
        """
        Determines if current seconds_remaining matches a notification milestone
        that has not yet been notified.
        """
        milestones = cls.MILESTONES.get(priority_class, [0])
        for m in milestones:
            if m not in notified_milestones:
                # Milestone is active if seconds_remaining <= milestone + 1s tolerance
                if m == 0 and seconds_remaining <= 2:
                    return 0
                elif m > 0 and (m - 2) <= seconds_remaining <= (m + 2):
                    return m
        return None
