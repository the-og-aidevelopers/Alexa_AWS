"""Map a spoken sentence onto one of the four dose tools."""

from __future__ import annotations

import re
from typing import Any

HELP = (
    "You can register a person, say when they need medicine, ask what is due, "
    "say that a dose was taken or skipped, or ask how today went."
)

_SLOT_TIMES = {
    "morning": "08:00",
    "afternoon": "14:00",
    "evening": "20:00",
    "night": "21:00",
    "tonight": "21:00",
}

_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", re.I)
_CLOCK24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_HINTS = ("morning", "afternoon", "evening", "tonight", "night")
def normalize_hearing(utterance: str) -> str:
    """Fold common speech-to-text mistakes into words the router already understands."""
    text = utterance.lower().replace("'", "")
    text = re.sub(r"\bdo you\b", "due", text)
    text = re.sub(r"\bto day\b", "today", text)
    text = re.sub(r"\b(?:dew|doo|du)\b", "due", text)
    text = re.sub(r"\bknow\b", "now", text)
    text = re.sub(r"\b(?:mourning|warning)\b", "morning", text)
    text = re.sub(r"\b(?:mum|mother)\b", "mom", text)
    text = re.sub(r"\b(?:meds|medication|pill|pills)\b", "medicine", text)
    text = re.sub(r"\b(morning|evening|afternoon|night) on\b", r"\1 one", text)
    text = re.sub(r"\bwhat(?:s| is)? (?:due|you|the) now\b", "whats due now", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def route_utterance(utterance: str, schedules: list[dict[str, Any]]) -> dict[str, Any] | None:
    raw = " ".join(utterance.strip().split())
    if not raw:
        return None
    if re.search(r"\b(skip(?:ped)?|didn't take|did not take|didnt take)\b", raw, re.I):
        action_text, reason = _split_reason(raw)
    else:
        action_text, reason = raw, ""
    action_text = normalize_hearing(action_text)
    if not action_text:
        return None
    folded = action_text.lower()
    registered = _register_name(folded)
    if registered:
        return {"tool": "register_person", "arguments": {"name": registered}}
    medicine = _medicine_request(folded)
    if medicine:
        return {"tool": "add_medicine", "arguments": medicine}

    tool = _action(folded)
    if tool is None:
        return None

    person = _find_known(folded, [row["person_name"] for row in schedules])
    label = _find_known(folded, [row["dose_label"] for row in schedules])
    hint = _time_hint(action_text)

    if tool == "list_due_doses":
        arguments = {"person_name": person}
    elif tool == "summarize_day":
        arguments = {"person_name": person}
    elif tool == "dose_status":
        arguments = {"person_name": person, "dose_label": label, "time_hint": hint}
    else:
        status = "skipped" if tool == "log_skipped" else "taken"
        arguments = {
            "status": status,
            "person_name": person,
            "dose_label": label,
            "time_hint": hint,
            "reason": reason if status == "skipped" else "",
        }
        tool = "log_dose"
    return {"tool": tool, "arguments": arguments}


def _register_name(folded: str) -> str:
    if not re.search(r"\b(register|add this person|add a person|add another person)\b", folded):
        return ""
    match = re.search(r"\bas\s+(.+)$", folded)
    if not match:
        return ""
    return _title_name(match.group(1))


def _medicine_request(folded: str) -> dict[str, str] | None:
    match = re.search(
        r"^(?P<person>.+?)\s+(?:needs|has)\s+to\s+take\s+(?P<label>.+?)\s+(?:at|in)\s+(?P<when>.+)$",
        folded,
    )
    if not match:
        return None
    person = _title_name(match.group("person"))
    label = _medicine_label(match.group("label"))
    times = _clock_list(match.group("when"))
    if not person or not label or not times:
        return None
    return {"person_name": person, "dose_label": label, "times": ",".join(times)}


def _medicine_label(text: str) -> str:
    words = [
        word
        for word in text.split()
        if word not in {"his", "her", "their", "the", "a", "an", "some", "this"}
    ]
    if not words:
        return "medicine"
    return " ".join(words)


def _clock_list(text: str) -> list[str]:
    clocks: list[str] = []
    for match in _CLOCK.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        meridian = match.group(3).lower().replace(".", "")
        if meridian == "pm" and hour < 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            clocks.append(f"{hour:02d}:{minute:02d}")
    if clocks:
        return list(dict.fromkeys(clocks))
    for hint, clock in _SLOT_TIMES.items():
        if re.search(rf"\b{hint}\b", text):
            clocks.append(clock)
    return list(dict.fromkeys(clocks))


def _title_name(text: str) -> str:
    skip = {"him", "her", "them", "please", "the", "a", "person"}
    words = [word for word in re.findall(r"[a-z]+(?:[-'][a-z]+)?", text.lower()) if word not in skip]
    return " ".join(word.capitalize() for word in words)


def _action(folded: str) -> str | None:
    if any(phrase in folded for phrase in ("how did today", "how today went", "summarize", "summary")):
        return "summarize_day"
    if any(phrase in folded for phrase in ("skip", "didn't take", "did not take", "didnt take")):
        return "log_skipped"
    if ("did " in f" {folded}" or folded.startswith("has ") or " has " in f" {folded}") and "take" in folded:
        return "dose_status"
    if folded.startswith("status") or "dose status" in folded:
        return "dose_status"
    if any(phrase in folded for phrase in ("i took", "i have taken", "i've taken", "ive taken")):
        return "log_taken"
    if any(
        phrase in folded
        for phrase in ("what's due", "whats due", "what is due", "due now", "what do i need", "what should i take")
    ):
        return "list_due_doses"
    if folded in {"due", "what's next", "whats next", "what is next"}:
        return "list_due_doses"
    return None


def _split_reason(text: str) -> tuple[str, str]:
    lowered = text.lower()
    because = lowered.find(" because ")
    if because != -1:
        return text[:because].strip(), text[because + len(" because ") :].strip()
    comma = text.find(",")
    if comma != -1:
        return text[:comma].strip(), text[comma + 1 :].strip()
    return text, ""


def _find_known(folded: str, values: list[str]) -> str:
    unique = sorted({value.strip() for value in values if value.strip()}, key=len, reverse=True)
    for value in unique:
        if value.lower() in folded:
            return value
    return ""


def _time_hint(text: str) -> str:
    match = _CLOCK.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        meridian = match.group(3).lower().replace(".", "")
        if meridian == "pm" and hour < 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    folded = text.lower()
    for hint in _HINTS:
        if re.search(rf"\b{hint}\b", folded):
            return hint
    match24 = _CLOCK24.search(text)
    if match24 and not _CLOCK.search(text):
        return f"{int(match24.group(1)):02d}:{match24.group(2)}"
    return ""
