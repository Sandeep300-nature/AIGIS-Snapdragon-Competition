import time
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional

class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"

class Task:
    """
    Represents a task within a conversation session.
    Manages explicit task states, step history, and task context.
    Focused purely on state representation without language/parsing logic.
    """
    def __init__(self, session_id: str, name: str, intent: str = "GENERAL_AI", context: Optional[Dict[str, Any]] = None):
        self.task_id: str = f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.session_id: str = session_id
        self.name: str = name
        self.intent: str = intent
        self.status: TaskStatus = TaskStatus.CREATED
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.context: Dict[str, Any] = context or {}
        self.step_history: List[Dict[str, Any]] = []
        self.state_reason: Optional[str] = None

    def set_active(self):
        self.status = TaskStatus.ACTIVE
        self.updated_at = time.time()

    def add_step(self, user_prompt: str, ai_reply: str):
        self.step_history.append({
            "user": user_prompt,
            "assistant": ai_reply,
            "timestamp": time.time()
        })
        if self.status != TaskStatus.ACTIVE:
            self.status = TaskStatus.ACTIVE
        self.updated_at = time.time()

    def pause(self, reason: Optional[str] = None):
        self.status = TaskStatus.PAUSED
        self.state_reason = reason
        self.updated_at = time.time()

    def mark_waiting_for_user(self, reason: Optional[str] = None):
        self.status = TaskStatus.WAITING_FOR_USER
        self.state_reason = reason
        self.updated_at = time.time()

    def resume(self):
        self.status = TaskStatus.ACTIVE
        self.state_reason = None
        self.updated_at = time.time()

    def complete(self, result_summary: Optional[str] = None):
        self.status = TaskStatus.COMPLETED
        if result_summary:
            self.context["result_summary"] = result_summary
        self.updated_at = time.time()

    def cancel(self, reason: Optional[str] = None):
        self.status = TaskStatus.CANCELED
        self.state_reason = reason
        self.updated_at = time.time()

    def fail(self, error_message: Optional[str] = None):
        self.status = TaskStatus.FAILED
        if error_message:
            self.context["error_message"] = error_message
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "name": self.name,
            "intent": self.intent,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context": self.context,
            "step_count": len(self.step_history),
            "state_reason": self.state_reason
        }

class TaskEngine:
    """
    Task Engine — State Machine & Task Stack Manager
    Focused strictly on task state management, state transitions, and task stack persistence.
    Does NOT perform string parsing, regex matching, or language interpretation.
    """

    def __init__(self):
        # session_id -> List[Task]
        self.session_tasks: Dict[str, List[Task]] = {}
        # session_id -> Task (currently active or focused task)
        self.active_tasks: Dict[str, Optional[Task]] = {}

    def get_all_tasks(self, session_id: str) -> List[Task]:
        return self.session_tasks.get(session_id, [])

    def get_active_task(self, session_id: str) -> Optional[Task]:
        task = self.active_tasks.get(session_id)
        if task and task.status == TaskStatus.ACTIVE:
            return task
        return None

    def get_paused_or_waiting_tasks(self, session_id: str) -> List[Task]:
        all_t = self.get_all_tasks(session_id)
        return [t for t in all_t if t.status in (TaskStatus.PAUSED, TaskStatus.WAITING_FOR_USER)]

    def create_task(self, session_id: str, name: str, intent: str = "GENERAL_AI", context: Optional[Dict[str, Any]] = None) -> Task:
        # Pause any current active task when a new distinct task is created
        current_active = self.get_active_task(session_id)
        if current_active and current_active.name.lower() != name.lower():
            current_active.pause(reason=f"New task created: {name}")

        new_task = Task(session_id=session_id, name=name, intent=intent, context=context)
        new_task.set_active()
        if session_id not in self.session_tasks:
            self.session_tasks[session_id] = []
        self.session_tasks[session_id].append(new_task)
        self.active_tasks[session_id] = new_task
        return new_task

    def pause_active_task(self, session_id: str, reason: Optional[str] = None) -> Optional[Task]:
        active = self.get_active_task(session_id)
        if active:
            active.pause(reason=reason or "Task paused")
            self.active_tasks[session_id] = None
            return active
        return None

    def set_active_task_waiting(self, session_id: str, reason: Optional[str] = None) -> Optional[Task]:
        active = self.get_active_task(session_id)
        if active:
            active.mark_waiting_for_user(reason=reason or "Waiting for user")
            self.active_tasks[session_id] = None
            return active
        return None

    def resume_task(self, session_id: str, task_id: Optional[str] = None) -> Optional[Task]:
        candidates = self.get_paused_or_waiting_tasks(session_id)
        if not candidates:
            return None

        target_task = None
        if task_id:
            for t in candidates:
                if t.task_id == task_id:
                    target_task = t
                    break
        else:
            target_task = sorted(candidates, key=lambda x: x.updated_at, reverse=True)[0]

        if target_task:
            current_active = self.get_active_task(session_id)
            if current_active and current_active.task_id != target_task.task_id:
                current_active.pause(reason=f"Resuming task: {target_task.name}")

            target_task.resume()
            self.active_tasks[session_id] = target_task
            return target_task
        return None

    def complete_active_task(self, session_id: str, result_summary: Optional[str] = None) -> Optional[Task]:
        active = self.get_active_task(session_id)
        if active:
            active.complete(result_summary)
            self.active_tasks[session_id] = None

            # Auto-resume previously paused task if available
            paused = self.get_paused_or_waiting_tasks(session_id)
            if paused:
                most_recent_paused = sorted(paused, key=lambda x: x.updated_at, reverse=True)[0]
                most_recent_paused.resume()
                self.active_tasks[session_id] = most_recent_paused

            return active
        return None

    def cancel_active_task(self, session_id: str, reason: Optional[str] = None) -> Optional[Task]:
        active = self.get_active_task(session_id)
        if active:
            active.cancel(reason=reason or "Task canceled by user")
            self.active_tasks[session_id] = None

            paused = self.get_paused_or_waiting_tasks(session_id)
            if paused:
                most_recent_paused = sorted(paused, key=lambda x: x.updated_at, reverse=True)[0]
                most_recent_paused.resume()
                self.active_tasks[session_id] = most_recent_paused

            return active
        return None

    def fail_active_task(self, session_id: str, error_message: Optional[str] = None) -> Optional[Task]:
        active = self.get_active_task(session_id)
        if active:
            active.fail(error_message)
            self.active_tasks[session_id] = None
            return active
        return None

    def record_turn(self, session_id: str, user_prompt: str, ai_reply: str):
        active = self.get_active_task(session_id)
        if active:
            active.add_step(user_prompt, ai_reply)

    def get_task_context_summary(self, session_id: str) -> str:
        """
        Formats current task states and task stack for LLM prompt injection.
        """
        active = self.get_active_task(session_id)
        paused = self.get_paused_or_waiting_tasks(session_id)

        if not active and not paused:
            return ""

        lines = ["TASK ENGINE STATE:"]
        if active:
            lines.append(f"- Active Task: '{active.name}' [State: {active.status.value}, Intent: {active.intent}, Steps: {len(active.step_history)}]")
            if active.step_history:
                last_step = active.step_history[-1]
                lines.append(f"  - Last Step: User: '{last_step['user']}' | AI: '{last_step['assistant'][:100]}...'")
        else:
            lines.append("- Active Task: None")

        if paused:
            paused_info = [f"'{t.name}' [State: {t.status.value}]" for t in paused[-3:]]
            lines.append(f"- Paused/Waiting Tasks: {', '.join(paused_info)}")

        return "\n".join(lines)
