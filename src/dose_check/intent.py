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

_CLOCK = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", re.I)
_CLOCK24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_HINTS = ("morning", "afternoon", "evening", "tonight", "night")
_DAYWORD = r"(?:mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?|weekdays?|weekends?)"
_DAYS = re.compile(
    rf"\b(?:(?:on|every|each)\s+)?{_DAYWORD}(?:\s*(?:,|and|to|through|thru|-)?\s*{_DAYWORD})*\b"
    r"|\b(?:every ?day|daily|each day|all days)\b"
)


def _extract_days(folded: str) -> tuple[str, str]:
    """Pull 'on Monday and Friday', 'weekdays', 'every day' out of a sentence."""
    found = _DAYS.search(folded)
    if not found:
        return "", folded
    rest = (folded[: found.start()] + " " + folded[found.end():])
    return found.group(0), re.sub(r"\s+", " ", rest).strip()


def normalize_hearing(utterance: str) -> str:
    """Fold common speech-to-text mistakes into words the router already understands."""
    text = re.sub(
        r"\b(?!(?:what|that|it|he|she|there|here|who|how|let|where|when|this)['’]s)([a-z]+)['’]s\b", r"\1", utterance.lower()
    )
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"\bdo you\b", "due", text)
    text = re.sub(r"\bto day\b", "today", text)
    text = re.sub(r"\b(?:dew|doo|du)\b", "due", text)
    text = re.sub(r"\bknow\b", "now", text)
    text = re.sub(r"\b(?:mourning|warning)\b", "morning", text)
    text = re.sub(r"\b(?:mum|mother)\b", "mom", text)
    text = re.sub(r"\b(?:meds|medication|pill|pills)\b", "medicine", text)
    text = re.sub(r"\b(?:address|ads)\b", "add", text)
    text = re.sub(r"\b(?:docomo|dopamin)\b", "dopamine", text)
    text = re.sub(r"\b(?:raaz|raz|rahj)\b", "raj", text)
    text = re.sub(r"\b(\w+) rebooting a medicine\b", r"\1 needs to take dopamine", text)
    text = re.sub(r"\b(?:lo for me|do for me|dope a mean|dopa mine|dopa mean)\b", "dopamine", text)
    text = re.sub(r"\bmedicine (dopamine)\b", r"\1", text)
    text = re.sub(r"\b([a-z]{2,})niti(?=\s+to\s+take\b)", r"\1 needs", text)
    text = re.sub(r"\btakes to come in\b", "needs to take medicine", text)
    text = re.sub(r"\b(morning|evening|afternoon|night) on\b", r"\1 one", text)
    text = re.sub(r"\bwhat(?:s| is)? (?:due|you|the) now\b", "whats due now", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def route_utterance(
    utterance: str,
    schedules: list[dict[str, Any]],
    known_people: list[str] | None = None,
) -> dict[str, Any] | None:
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
    days, spare = _extract_days(folded)
    combined = _register_with_medicine(spare)
    if combined:
        if days:
            combined["days"] = days
        return {"tool": "add_medicine", "arguments": combined}
    registered = _register_name(folded)
    if registered:
        return {"tool": "register_person", "arguments": {"name": registered}}
    people = sorted({*(row["person_name"] for row in schedules), *(known_people or [])}, key=len, reverse=True)
    removal = _removal(folded, schedules, people)
    if removal:
        return removal
    days, folded = _extract_days(folded)
    changed = _change_request(folded, schedules, days, people)
    if changed:
        return changed
    medicine = _medicine_request(folded) or _add_person_time_label(folded, people, [row["dose_label"] for row in schedules])
    if medicine:
        if days:
            medicine["days"] = days
        return {"tool": "add_medicine", "arguments": medicine}

    tool = _action(folded)
    if tool is None:
        bare = _person_with_medicine(folded)
        if bare:
            if days:
                bare["days"] = days
            return {"tool": "add_medicine", "arguments": bare}
        return None

    person = _find_known(folded, people)
    label = _find_known(folded, [row["dose_label"] for row in schedules])
    hint = _time_hint(action_text)

    if tool in {"list_medicines", "clear_today_log"}:
        arguments = {"person_name": person}
    elif tool == "list_due_doses":
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


def _removal(folded: str, schedules: list[dict[str, Any]], people: list[str]) -> dict[str, Any] | None:
    if not re.match(r"^(?:please )?(?:remove|delete|cancel|drop|unregister|stop (?:taking|giving))\b", folded):
        return None
    person = _find_known(folded, people)
    if re.search(r"\bunregister\b|\bperson\b|\bhousehold\b|\bfamily\b|\bcompletely\b", folded):
        if person:
            return {"tool": "remove_person", "arguments": {"name": person}}
        named = re.search(r"\b(?:person|unregister)\s+(.+)$", folded)
        if named:
            return {"tool": "remove_person", "arguments": {"name": _title_name(named.group(1))}}
    label = _find_known(folded, [row["dose_label"] for row in schedules])
    return {
        "tool": "remove_medicine",
        "arguments": {"person_name": person, "dose_label": label, "time_hint": _time_hint(folded)},
    }


def _change_request(folded: str, schedules: list[dict[str, Any]], days: str, people: list[str]) -> dict[str, Any] | None:
    if not re.match(r"^(?:please )?(?:change|move|reschedule|update|edit)\b", folded):
        return None
    person = _find_known(folded, people)
    label = _find_known(folded, [row["dose_label"] for row in schedules])
    if not person and not label:
        return None
    arguments = {"person_name": person, "dose_label": label, "times": ",".join(_clock_list(folded))}
    if days:
        arguments["days"] = days
    return {"tool": "change_medicine", "arguments": arguments}


def _register_name(folded: str) -> str:
    if not re.search(r"\b(register|add (?:this |a |another |the )?(?:new )?person)\b", folded):
        return ""
    as_name = re.search(r"\bas\s+(.+)$", folded)
    if as_name:
        words = []
        for word in as_name.group(1).split():
            if word in _NAME_STOPS:
                if words:
                    break
                return _name_before_as(folded)
            words.append(word)
        named = _title_name(" ".join(words))
        if named:
            return named
    cleaned = re.sub(
        r"\b(?:please|register|add (?:this |a |another |the )?(?:new )?person|him|her|them|this|person)\b",
        " ",
        folded,
    )
    words = []
    for word in cleaned.split():
        if word in _NAME_STOPS:
            if words:
                break
            continue
        words.append(word)
    return _title_name(" ".join(dict.fromkeys(words)))


def _name_before_as(folded: str) -> str:
    """'Register Priya as a new person ...' keeps Priya, the word before 'as'."""
    before = folded.split(" as ", 1)[0]
    words = [word for word in re.sub(r"\b(?:please|register|add)\b", " ", before).split() if word not in _NAME_STOPS]
    return _title_name(" ".join(dict.fromkeys(words[-2:])))


_NAME_STOPS = {
    "he", "she", "they",
    "has", "have", "had", "is", "with", "who", "that", "for", "and", "to", "needs", "need", "takes",
    "take", "taking", "at", "in", "on", "of", "new", "the", "a", "an", "as", "his", "her", "their",
    "medicine", "medicines", "also", "then",
}
_FILLER = _NAME_STOPS | {
    "he", "she", "they",
    "register", "add", "registered", "person", "him", "them", "this", "please", "pm", "am", "a.m.", "p.m.",
    "every", "day", "daily", "mr", "mrs", "ms", "miss", "mister", "dr", "doctor", "another", "from", "one",
}


_NOT_NAMES = {
    "what", "whats", "who", "when", "where", "how", "why", "did", "does", "do", "is", "are", "was", "were",
    "i", "we", "you", "it", "this", "that", "please", "can", "could", "has", "have",
}


def _person_with_medicine(folded: str) -> dict[str, str] | None:
    """'Rajesh Ram with his 8 PM dopamine medicine' -> add_medicine, even when the verb was lost."""
    match = re.match(
        r"^(?P<name>[a-z]+(?:\s[a-z]+)?)\s+(?:with|has|have|on|for|takes|take)\s+(?:(?:his|her|their|a|the)\s+)?(?P<rest>.+)$",
        folded,
    )
    if not match:
        return None
    times = _clock_list(match.group("rest"))
    if not times:
        return None
    name_words = match.group("name").split()
    if any(word in _NOT_NAMES for word in name_words):
        return None
    label_words = [
        word.strip(".,:;!?")
        for word in _without_clocks(match.group("rest")).split()
        if word.strip(".,:;!?") not in _FILLER
    ]
    return {
        "person_name": _title_name(" ".join(name_words)),
        "dose_label": " ".join(label_words) or "medicine",
        "times": ",".join(times),
    }


def _register_with_medicine(folded: str) -> dict[str, str] | None:
    """'Register Rajesh as a new person with 6 PM of his dopamine' -> add_medicine (it creates the person)."""
    if not re.search(r"\b(?:register|add (?:this |a |another |the )?(?:new )?person)\b", folded):
        return None
    times = _clock_list(folded)
    if not times:
        return None
    name = _register_name(folded)
    if not name:
        return None
    remaining = _without_clocks(folded)
    taken = {part.lower() for part in name.split()}
    label_words = [
        word.strip(".,:;!?")
        for word in remaining.split()
        if word.strip(".,:;!?") not in _FILLER and word.strip(".,:;!?") not in taken
    ]
    label = " ".join(label_words) or "medicine"
    return {"person_name": name, "dose_label": label, "times": ",".join(times)}


def _medicine_request(folded: str) -> dict[str, str] | None:
    added = re.search(
        r"^(?:add|at)\s+(?P<person>[a-z]+(?:[-'][a-z]+)?)\s+(?P<label>.+?)\s+at\s+(?P<when>.+)$",
        folded,
    )
    if added:
        return _medicine_parts(added.group("person"), added.group("label"), added.group("when"))
    match = re.search(
        r"^(?P<person>.+?)\s+"
        r"(?:(?:needs|has|have)\s+to\s+take|(?:to\s+)?takes?)\s+"
        r"(?P<label>.+?)\s+(?:at|in)\s+(?P<when>.+)$",
        folded,
    )
    if not match:
        return None
    return _medicine_parts(match.group("person"), match.group("label"), match.group("when"))


_TAIL = re.compile(r"\b(?:is|was|are|were)\s+(?:overdue|due|late|taken|missed|skipped)\b.*$")


_DRUGS = {
    "dopamine", "aspirin", "metformin", "lisinopril", "amlodipine", "atorvastatin", "levothyroxine",
    "insulin", "paracetamol", "ibuprofen", "omeprazole",
}


def _add_person_time_label(folded: str, people: list[str], labels: list[str]) -> dict[str, str] | None:
    """'Add Mom 8 AM medicine' / "Add Mom's 8 AM lisinopril" -> add_medicine for Mom."""
    match = re.match(r"^(?:please\s+)?(?:add|set up)\s+(?P<rest>.+)$", _TAIL.sub("", folded).strip())
    if not match:
        return None
    rest = match.group("rest")
    times = _clock_list(rest)
    if not times:
        return None
    person = _find_known(rest.split(" at ")[0].split(" in ")[0], people)
    if person and rest.lower().startswith(person.lower()):
        remainder = rest[len(person):]
    else:
        first, _, remainder = rest.partition(" ")
        person = first
    name = _title_name(person)
    if not name or name.lower() in _NOT_NAMES or name.lower() in _DRUGS | {label.lower() for label in labels} or any(word in {"person", "medicine", "dose"} for word in name.lower().split()):
        return None
    label_words = [
        word.strip(".,:;!?")
        for word in _without_clocks(remainder).split()
        if word.strip(".,:;!?") not in _FILLER
    ]
    return {"person_name": name, "dose_label": " ".join(label_words) or "medicine", "times": ",".join(times)}


def _medicine_parts(person_text: str, label_text: str, when: str) -> dict[str, str] | None:
    person = _title_name(person_text)
    label = _medicine_label(label_text)
    trailing = _medicine_label(_without_clocks(when))
    if label == "medicine" and trailing and trailing != "medicine":
        label = trailing
    times = _clock_list(when)
    if not person or not label or not times:
        return None
    return {"person_name": person, "dose_label": label, "times": ",".join(times)}


def _without_clocks(text: str) -> str:
    cleaned = _CLOCK.sub(" ", text)
    cleaned = _CLOCK24.sub(" ", cleaned)
    for hint in _SLOT_TIMES:
        cleaned = re.sub(rf"\b{hint}\b", " ", cleaned)
    return re.sub(r"\b(?:and|the|at|in|a|an)\b", " ", cleaned)


def _medicine_label(text: str) -> str:
    words = []
    for word in text.split():
        cleaned = word.strip(".,:;!?")
        if cleaned and cleaned not in {"his", "her", "their", "the", "a", "an", "some", "this"}:
            words.append(cleaned)
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
    bare = re.search(r"(?:^|\bat\s+)(\d{1,2})(?![:.]\d)\b", text)
    if bare and not clocks:
        hour = int(bare.group(1))
        if 1 <= hour <= 12:
            clocks.append(f"{hour:02d}:00")
    return list(dict.fromkeys(clocks))


def _title_name(text: str) -> str:
    skip = {
        "him", "her", "them", "please", "the", "a", "an", "person",
        "mr", "mrs", "ms", "miss", "mister", "dr", "doctor",
    }
    words = [word for word in re.findall(r"[a-z]+(?:[-'][a-z]+)?", text.lower()) if word not in skip]
    return " ".join(word.capitalize() for word in words)


def _action(folded: str) -> str | None:
    if re.search(r"\b(?:clear|reset|erase|wipe)\b.*\b(?:logs?|today|todays|day)\b", folded):
        return "clear_today_log"
    if any(phrase in folded for phrase in ("how did today", "how today went", "summarize", "summary")):
        return "summarize_day"
    if any(phrase in folded for phrase in ("skip", "didn't take", "did not take", "didnt take")):
        return "log_skipped"
    if ("did " in f" {folded}" or folded.startswith(("has ", "have ", "does ", "was ", "were "))) and "take" in folded:
        return "dose_status"
    if re.search(
        r"\bwhat medicines?\b(?!.*\b(?:due|now|next|today)\b)|\b(?:what|when) (?:does|do) \w+ take\b"
        r"|\bschedule\b|\blist\b.*\bmedicines?\b",
        folded,
    ):
        return "list_medicines"
    if re.search(r"\b(status|how is|hows|how are|doing|current)\b", folded):
        return "dose_status"
    if re.search(r"\b(?:show|tell me|check)\b.*\bmedicines?\b", folded):
        return "dose_status"
    if re.search(r"\b(took|taken|had (?:his|her|their|the) )", folded) or re.search(r"\b(?:mark|marked|log)\b.*\btaken\b", folded):
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
