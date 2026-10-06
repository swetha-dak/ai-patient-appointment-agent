"""Qwen structured extraction plus Python validation. SQLite remains the source of truth."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from backend.agent.ollama_client import OllamaError, chat, ollama_is_available
from backend.agent.planner import extract_from_message as extract_with_regex
from backend.agent.policy import get_policy
from backend.agent.prompts import EXTRACTION_PROMPT
from backend.models.extraction import UserExtraction

PATIENT_ID_RE = re.compile(r"\bPAT-\d+\b", re.I)
DOCTOR_ID_RE = re.compile(r"\bDOC-\d+\b", re.I)
APPOINTMENT_ID_RE = re.compile(r"\bAPT-\d+\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
DOCTOR_NAME_RE = re.compile(r"\bdr\.?\s+([A-Za-z]+)\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
TIME_24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
MONTH_DAY_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.I,
)
WEEKDAY_RE = re.compile(
    r"\b(next|this)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
AMBIGUOUS_DATE_RE = re.compile(r"\b(next week|sometime|this week)\b", re.I)
JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
INTENT_MAP = {
    "book": "book",
    "cancel": "cancel",
    "reschedule": "reschedule",
    "availability": "book",
}


def _normalize_time(hour: int, minute: int, meridian: str | None) -> str | None:
    if meridian:
        meridian = meridian.lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_time_text(text: str | None) -> str | None:
    if not text:
        return None
    ampm = TIME_RE.search(text)
    if ampm:
        return _normalize_time(int(ampm.group(1)), int(ampm.group(2) or 0), ampm.group(3))
    time_24 = TIME_24_RE.search(text)
    if time_24:
        return f"{int(time_24.group(1)):02d}:{time_24.group(2)}"
    return None


def resolve_date_text(text: str | None, *, today: date | None = None) -> tuple[str | None, bool]:
    """Resolve spoken dates in Python. Returns (iso_date, is_relative)."""
    if not text or AMBIGUOUS_DATE_RE.search(text):
        return None, False
    today = today or date.today()
    iso = ISO_DATE_RE.search(text)
    if iso:
        return iso.group(1), False

    lowered = text.lower()
    if re.search(r"\btoday\b", lowered):
        return today.isoformat(), True
    if re.search(r"\btomorrow\b", lowered):
        return (today + timedelta(days=1)).isoformat(), True

    weekday = WEEKDAY_RE.search(text)
    if weekday:
        qualifier = (weekday.group(1) or "next").lower()
        wanted = WEEKDAYS[weekday.group(2).lower()]
        delta = (wanted - today.weekday()) % 7
        if qualifier == "next" and delta == 0:
            delta = 7
        return (today + timedelta(days=delta)).isoformat(), True

    month_day = MONTH_DAY_RE.search(text)
    if month_day:
        month = MONTHS[month_day.group(1).lower()]
        day = int(month_day.group(2))
        try:
            resolved = date(today.year, month, day)
        except ValueError:
            return None, False
        if resolved < today:
            try:
                resolved = date(today.year + 1, month, day)
            except ValueError:
                return None, False
        return resolved.isoformat(), True
    return None, False


def _id_in_text(pattern: re.Pattern[str], value: str | None, text: str) -> str | None:
    if not value:
        return None
    match = pattern.search(value) or pattern.search(text)
    if not match:
        return None
    found = match.group(0).upper()
    if found.lower() not in text.lower() and found.lower() not in (value or "").lower():
        return None
    if found.lower() not in text.lower():
        return None
    return found


def _doctor_name(value: str | None, text: str) -> str | None:
    source = " ".join(part for part in (value, text) if part)
    match = DOCTOR_NAME_RE.search(source)
    if not match:
        return None
    last = match.group(1).title()
    if last.lower() not in text.lower():
        return None
    return f"Dr. {last}"


def apply_policy_date(iso_date: str | None, is_relative: bool) -> dict[str, Any]:
    if not iso_date:
        return {}
    policy = get_policy()
    if is_relative and (not policy.get("resolve_relative_dates") or policy.get("require_iso_date")):
        return {}
    return {"date": iso_date, "date_is_relative": is_relative}


def _parse_extraction_json(raw: str) -> UserExtraction | None:
    blob = raw.strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*|\s*```$", "", blob, flags=re.I | re.S)
    match = JSON_BLOCK_RE.search(blob)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return UserExtraction.model_validate(payload)
    except Exception:
        return None


def extract_with_qwen(text: str) -> UserExtraction | None:
    if not ollama_is_available():
        return None
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": text},
    ]
    try:
        reply = chat(messages, response_format="json")
    except OllamaError:
        return None
    return _parse_extraction_json(str(reply.get("content") or ""))


def _merge_qwen(updates: dict[str, Any], parsed: UserExtraction, text: str) -> dict[str, Any]:
    mapped = INTENT_MAP.get(parsed.intent or "")
    if mapped and "appointment_intent" not in updates:
        updates["appointment_intent"] = mapped

    patient_id = _id_in_text(PATIENT_ID_RE, parsed.patient_id, text)
    if patient_id:
        updates["patient_id"] = patient_id
    doctor_id = _id_in_text(DOCTOR_ID_RE, parsed.doctor_id, text)
    if doctor_id:
        updates["doctor_id"] = doctor_id
    appointment_id = _id_in_text(APPOINTMENT_ID_RE, parsed.appointment_id, text)
    if appointment_id:
        updates["appointment_id"] = appointment_id

    doctor_name = _doctor_name(parsed.doctor_name, text)
    if doctor_name:
        updates["doctor_name"] = doctor_name

    if parsed.patient_name and parsed.patient_name.lower() in text.lower():
        updates.setdefault("patient_name", parsed.patient_name.strip())

    if "date" not in updates:
        iso, relative = resolve_date_text(parsed.date_text or text)
        updates.update(apply_policy_date(iso, relative))
    if "time" not in updates:
        parsed_time = parse_time_text(parsed.time_text) or parse_time_text(text)
        if parsed_time:
            updates["time"] = parsed_time
    return updates


def extract_from_message(text: str) -> dict[str, Any]:
    """Regex + Python date resolution, with optional Qwen fill-in. Not a DB write."""
    updates = extract_with_regex(text)
    if "date" not in updates:
        iso, relative = resolve_date_text(text)
        updates.update(apply_policy_date(iso, relative))
    if updates.get("doctor_name") and "appointment_intent" not in updates:
        updates["appointment_intent"] = "book"

    parsed = extract_with_qwen(text)
    if parsed is not None:
        updates = _merge_qwen(updates, parsed, text)
    return updates
