"""Safety and validation rules applied to user input and to everything the AI proposes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Optional

from pawpal_system import FREQUENCIES, PRIORITY_RANK, parse_time

MAX_INPUT_CHARS = 500
MAX_TITLE_CHARS = 60
MAX_SUGGESTED_MINUTES = 120
MAX_SUGGESTIONS = 6

EMERGENCY_PATTERNS = [
    r"\bpoison", r"\btoxic\b",
    # "ate chocolate", "just ate a bar of chocolate", "got into the raisins", "chewed my ibuprofen"
    r"\b(ate|eaten|eating|swallowed|chewed|licked|got into)\b.{0,40}\b(chocolate|grapes?|raisins?|xylitol|gum|"
    r"lil(y|ies)|onions?|garlic|antifreeze|rat bait|ibuprofen|advil|tylenol|acetaminophen|pills?|medication|medicine)",
    r"\bseizur", r"\bnot breathing\b", r"\btrouble breathing\b", r"\bcan'?t breathe\b", r"\bcollaps",
    r"\bbleeding\b", r"\bhit by (a )?car\b", r"\bunconscious\b", r"\bcan'?t (pee|urinate)\b",
    r"\bswallowed\b", r"\bemergency\b",
]
DOSE_REQUEST = re.compile(r"\b(how (much|many)|dose|dosage|dosing|mg|milligrams?|ml|millilit(er|re)s?|tablets? of)\b", re.I)
MED_WORDS = re.compile(
    r"\b(med|meds|medicine|medication|pill|pills|tablet|tablets|ibuprofen|advil|tylenol|acetaminophen|"
    r"aspirin|benadryl|diphenhydramine|insulin|antibiotic|antibiotics|painkiller|melatonin|dewormer|"
    r"prednisone|gabapentin|trazodone)\b",
    re.I,
)
# Numbers next to a dose unit, e.g. "5 mg", "2.5ml", "1/2 tablet".
DOSE_AMOUNT = re.compile(r"\b\d+([./]\d+)?\s?(mg|milligrams?|ml|millilit(er|re)s?|cc|tablets?|pills?|units?)\b", re.I)


def sanitize_text(text: Optional[str], max_chars: int = MAX_INPUT_CHARS) -> str:
    """Normalize user text: drop control characters, collapse whitespace, cap the length."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


@dataclass
class SafetyCheck:
    allowed: bool
    kind: str = "ok"  # ok | emergency | dosage | empty
    message: str = ""


def check_question(question: str) -> SafetyCheck:
    """Decide whether a care question can go to the advisor, or needs a fixed safe response instead."""
    q = question.lower()
    if not q.strip():
        return SafetyCheck(False, "empty", "Please type a question about your pet's care.")
    if any(re.search(p, q) for p in EMERGENCY_PATTERNS):
        return SafetyCheck(
            False,
            "emergency",
            "This sounds like it could be an emergency. Call your vet or the nearest 24-hour emergency "
            "animal hospital now. If your pet may have eaten something toxic, contact an animal poison "
            "control line. PawPal+ can't assess emergencies.",
        )
    if DOSE_REQUEST.search(q) and MED_WORDS.search(q):
        return SafetyCheck(
            False,
            "dosage",
            "PawPal+ won't suggest medication doses. The right amount depends on your pet's weight, health "
            "and the exact product, so please ask your vet or pharmacist. Never give human medicine to a "
            "pet without your vet's OK. I can help you schedule medication at a fixed time once you know the dose.",
        )
    return SafetyCheck(True)


def contains_dose_amount(text: str) -> bool:
    return bool(DOSE_AMOUNT.search(text or ""))


@dataclass
class Suggestion:
    """A validated task suggestion, ready to become a pawpal_system.Task."""

    title: str
    duration_minutes: int
    priority: str
    frequency: str
    preferred_time: Optional[str]
    source_id: str
    rationale: str


def validate_suggestion(raw: Any, allowed_sources: set[str]) -> tuple[Optional[Suggestion], str]:
    """Check one AI-proposed task. Returns (suggestion, "") or (None, reason it was rejected)."""
    if not isinstance(raw, dict):
        return None, "not an object"
    title = sanitize_text(raw.get("title"), MAX_TITLE_CHARS)
    if not title:
        return None, "missing title"
    try:
        minutes = int(raw.get("duration_minutes"))
    except (TypeError, ValueError):
        return None, f"'{title}': duration is not a number"
    if not 1 <= minutes <= MAX_SUGGESTED_MINUTES:
        return None, f"'{title}': duration {minutes} is outside 1-{MAX_SUGGESTED_MINUTES} minutes"
    priority = str(raw.get("priority", "")).lower().strip()
    if priority not in PRIORITY_RANK:
        return None, f"'{title}': priority {priority!r} is not low/medium/high"
    frequency = str(raw.get("frequency", "once")).lower().strip()
    if frequency not in FREQUENCIES:
        return None, f"'{title}': frequency {frequency!r} is not once/daily/weekly"
    at = raw.get("preferred_time") or None
    if at is not None:
        try:
            parse_time(str(at))
        except ValueError:
            return None, f"'{title}': preferred_time {at!r} is not HH:MM"
        at = str(at).strip()
    source = str(raw.get("source_id", "")).strip()
    if source not in allowed_sources:
        return None, f"'{title}': cites {source!r}, which was not one of the retrieved sources"
    rationale = sanitize_text(raw.get("rationale"), 240)
    if contains_dose_amount(title) or contains_dose_amount(rationale):
        return None, f"'{title}': mentions a medication amount, which PawPal+ never suggests"
    return Suggestion(title, minutes, priority, frequency, at, source, rationale), ""
