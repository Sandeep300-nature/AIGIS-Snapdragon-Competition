import re
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

class ReminderParser:
    """
    Production-Grade Natural Language Reminder Parser.
    Strictly enforces Rules 1-4:
    - Rule 1: No silent +30 minute default fallback. Returns (None, "TIME_MISSING") if unparseable.
    - Rule 2: Relative reminders have highest priority and calculate Current Time + Duration immediately.
    - Rule 3: Absolute parsing runs only if relative parser fails.
    - Rule 4: Extract clean titles without prompt noise.
    """

    MONTH_MAP = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12
    }

    WEEKDAY_MAP = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6
    }

    @classmethod
    def parse_reminder_request(cls, text: str) -> Dict[str, Any]:
        now = datetime.now()
        lowered = text.lower().strip()

        # Determine Category Type
        category = "reminder"
        if any(w in lowered for w in ["meeting", "conference", "standup", "sync", "interview"]):
            category = "meeting"
        elif any(w in lowered for w in ["dentist", "doctor", "appointment", "clinic", "checkup"]):
            category = "appointment"
        elif any(w in lowered for w in ["birthday", "bday", "anniversary"]):
            category = "birthday"
        elif any(w in lowered for w in ["bill", "rent", "fee", "payment", "electricity"]):
            category = "bill"
        elif any(w in lowered for w in ["medication", "medicine", "pill", "dose"]):
            category = "medication"
        elif any(w in lowered for w in ["task", "submit", "assignment", "project", "report"]):
            category = "task"

        # Determine Priority Class
        priority = "normal"
        if any(w in lowered for w in ["urgent", "important", "interview", "medication", "flight", "emergency", "meeting"]):
            priority = "high"

        target_dt, reminder_type_name = cls.parse_datetime_expression(text, now)
        title = cls.extract_clean_title(text)

        return {
            "title": title,
            "description": text,
            "type": category,
            "datetime": target_dt.strftime("%Y-%m-%dT%H:%M:%S") if target_dt else None,
            "priority": priority,
            "parsing_mode": reminder_type_name
        }

    @classmethod
    def parse_datetime_expression(cls, text: str, now: datetime) -> Tuple[Optional[datetime], str]:
        lowered = text.lower().strip()

        # ----------------------------------------------------
        # 1. TYPE 3: HYBRID (e.g. "10 minutes after 1 PM", "2 hours after tomorrow 9 AM")
        # ----------------------------------------------------
        hybrid_match = re.search(r'(\d+)\s*(secs?|seconds?|mins?|minutes?|hours?|hrs?)\s+after\s+(.*)', lowered)
        if hybrid_match:
            amount = int(hybrid_match.group(1))
            unit = hybrid_match.group(2)
            base_expr = hybrid_match.group(3)

            base_dt, _ = cls.parse_datetime_expression(base_expr, now)
            if base_dt:
                if "sec" in unit:
                    return base_dt + timedelta(seconds=amount), "HYBRID"
                elif "min" in unit:
                    return base_dt + timedelta(minutes=amount), "HYBRID"
                elif "hour" in unit or "hr" in unit:
                    return base_dt + timedelta(hours=amount), "HYBRID"

        # ----------------------------------------------------
        # 2. TYPE 1: RELATIVE (RULE 2: Highest Priority - Immediate Return)
        # Matches: "for 2 mins", "in 5 minutes", "after 30 seconds", "within 10 minutes", "2 mins", "30 seconds"
        # ----------------------------------------------------
        # ----------------------------------------------------
        # 2. TYPE 1: RELATIVE (RULE 2: Highest Priority - Immediate Return)
        # Matches: "for 2 mins", "in 5 minutes", "after 30 seconds", "within 10 minutes", "2 mins", "30s", "1m"
        # ----------------------------------------------------
        rel_match = re.search(r'\b(?:for|in|after|within)?\s*(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b', lowered)
        if rel_match:
            amount = int(rel_match.group(1))
            unit = rel_match.group(2)
            if unit in ["s", "sec", "secs", "second", "seconds"]:
                return now + timedelta(seconds=amount), "RELATIVE"
            elif unit in ["m", "min", "mins", "minute", "minutes"]:
                return now + timedelta(minutes=amount), "RELATIVE"
            elif unit in ["h", "hr", "hrs", "hour", "hours"]:
                return now + timedelta(hours=amount), "RELATIVE"
            elif unit in ["d", "day", "days"]:
                return now + timedelta(days=amount), "RELATIVE"

        # ----------------------------------------------------
        # 3. TYPE 2: ABSOLUTE (RULE 3: Runs ONLY if relative parser fails)
        # Matches: "at 5 PM", "tomorrow 8 AM", "Monday 10 AM", "August 25 4 PM"
        # ----------------------------------------------------
        hour = None
        minute = 0

        # Check explicit time: "at 5 PM", "10:30 AM", "at 14:00"
        time_match = re.search(r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', lowered)
        if not time_match:
            time_match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', lowered)

        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            meridiem = time_match.group(3)
            if meridiem:
                if meridiem == "pm" and hour < 12:
                    hour += 12
                elif meridiem == "am" and hour == 12:
                    hour = 0

        if "tonight" in lowered or "this evening" in lowered:
            if hour is None:
                hour = 20
        elif "noon" in lowered:
            if hour is None:
                hour = 12
        elif "morning" in lowered:
            if hour is None:
                hour = 9

        default_hour = 9 if hour is None else hour

        # Date: "tomorrow"
        if "tomorrow" in lowered:
            target_date = now.date() + timedelta(days=1)
            return datetime.combine(target_date, datetime.min.time()).replace(hour=default_hour, minute=minute), "ABSOLUTE"

        # Weekdays: "next Friday", "on Monday"
        for day_name, weekday_num in cls.WEEKDAY_MAP.items():
            if re.search(r'\b(next|this|on)?\s*' + day_name + r'\b', lowered):
                days_ahead = weekday_num - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                target_date = now.date() + timedelta(days=days_ahead)
                return datetime.combine(target_date, datetime.min.time()).replace(hour=default_hour, minute=minute), "ABSOLUTE"

        # Month date: "August 25", "25 August"
        month_pattern = r'\b(' + '|'.join(cls.MONTH_MAP.keys()) + r')\s+(\d{1,2})(?:st|nd|rd|th)?\b'
        m1 = re.search(month_pattern, lowered)
        if m1:
            month = cls.MONTH_MAP[m1.group(1)]
            day = int(m1.group(2))
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            return datetime(year, month, day, default_hour, minute), "ABSOLUTE"

        date_month_pattern = r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(' + '|'.join(cls.MONTH_MAP.keys()) + r')\b'
        m2 = re.search(date_month_pattern, lowered)
        if m2:
            day = int(m2.group(1))
            month = cls.MONTH_MAP[m2.group(2)]
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            return datetime(year, month, day, default_hour, minute), "ABSOLUTE"

        if hour is not None:
            target_dt = datetime.combine(now.date(), datetime.min.time()).replace(hour=hour, minute=minute)
            if target_dt <= now:
                target_dt += timedelta(days=1)
            return target_dt, "ABSOLUTE"

        # RULE 1: No silent default +30m fallback. Return TIME_MISSING if unparseable.
        return None, "TIME_MISSING"

    @classmethod
    def extract_clean_title(cls, text: str) -> str:
        t = text.strip()
        t = re.sub(r'[?\!\.]', '', t)
        t = re.sub(r'^(hey\s+)?(aigis|friday)?\s*(can\s+you\s+|can\s+u\s+|could\s+you\s+|please\s+)?(remind\s+me|schedule\s+a\s+reminder|schedule\s+reminder|schedule|set\s+a\s+reminder|set\s+reminder|set\s+an?\s+alarm|put\s+a\s+reminder|put\s+reminder|create\s+a\s+reminder|create\s+reminder|add\s+a\s+reminder|add\s+reminder|dont\s+let\s+me\s+forget|don\'t\s+let\s+me\s+forget|i\s+have\s+a)\s*', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'\b(in|after|for|within)\s+\d+\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'\b\d+\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\b', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(am|pm)?\b', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'\b(tomorrow|tonight|next\s+\w+|on\s+\w+)\b', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'^\s*(to|for|about)\s+', '', t, flags=re.IGNORECASE).strip()

        if not t or len(t) < 2 or t.lower() in ["reminder", "me", "set a reminder", "can u set a reminder", "set reminder", "alarm"]:
            return "Reminder"

        return t.capitalize()

