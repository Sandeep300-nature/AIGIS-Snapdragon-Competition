import uuid
from datetime import datetime
from typing import Optional, Dict, Any

class Reminder:
    def __init__(
        self,
        title: str,
        datetime_str: str,
        description: str = "",
        reminder_type: str = "reminder",
        priority: str = "normal",
        reminder_id: Optional[str] = None,
        created_at: Optional[str] = None,
        status: str = "pending",
        completed: bool = False,
        last_notified: Optional[str] = None
    ):
        self.id = reminder_id or str(uuid.uuid4())
        self.title = title
        self.description = description or title
        self.type = reminder_type.lower() if reminder_type else "reminder"
        self.datetime = datetime_str
        self.created_at = created_at or datetime.now().isoformat()
        self.status = status
        self.priority = priority.lower() if priority else "normal"
        self.completed = completed
        self.last_notified = last_notified

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "datetime": self.datetime,
            "created_at": self.created_at,
            "status": self.status,
            "priority": self.priority,
            "completed": self.completed,
            "last_notified": self.last_notified
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Reminder":
        return cls(
            reminder_id=data.get("id"),
            title=data.get("title", "Untitled Reminder"),
            description=data.get("description", ""),
            reminder_type=data.get("type", "reminder"),
            datetime_str=data.get("datetime", datetime.now().isoformat()),
            created_at=data.get("created_at"),
            status=data.get("status", "pending"),
            priority=data.get("priority", "normal"),
            completed=data.get("completed", False),
            last_notified=data.get("last_notified")
        )
