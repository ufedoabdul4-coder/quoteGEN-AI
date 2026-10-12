"""Classification helpers for content understanding.

Every test here answers one narrow question about a short string. They are kept
in one place so the understanding stage, the financial checker and the layout
engine can never disagree about *what counts as money*.

The ordering rule that protects the totals: a phone number, a date, a quantity
or a reference number must be recognised **before** money, because ``+234 803
000 0000`` and ``2,000,000`` share digits but mean entirely different things.
"""

from __future__ import annotations

import re

_CURRENCY_SYMBOLS = "$£€₦₹¥₽"
_SYMBOL_CLASS = re.escape(_CURRENCY_SYMBOLS)

#: A number *carrying* a currency mark on either side, e.g. ``$1,200.50`` or
#: ``1 200 NGN``. Anchored loosely; ``is_money`` applies the strict checks.
MARKED_MONEY_RE = re.compile(
    r"(?<![\w.])(?:[A-Z]{3}|[" + _SYMBOL_CLASS + r"])\s?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?(?![\w])"
    r"|"
    r"(?<![\w.])\d{1,3}(?:[,\s]\d{3})*(?:\.\d{1,2})?\s?(?:[A-Z]{3}|[" + _SYMBOL_CLASS + r"])(?![\w])"
)

#: A bare number that is *unambiguously* a money-like figure: it either groups
#: digits with a thousands separator (``450,000`` / ``1 200 000``) or carries two
#: decimal places (``450.00``). A plain integer such as ``450000`` is left out on
#: purpose, because without context it is indistinguishable from an ID, and the
#: understanding stage classifies those from their column instead.
BARE_MONEY_RE = re.compile(
    r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,3}(?:\s\d{3})+(?:\.\d{1,2})?|\d+\.\d{2})(?![\w])"
)

MONEY_RE = MARKED_MONEY_RE

PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}"
    r"(?:\s?(?:x|ext\.?)\s?\d{1,6})?"
)

DATE_RE = re.compile(
    r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{2,4}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{2,4}\b",
    re.I,
)

QTY_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:pcs?|units?|nos?\.?|sq\.?\s?m|m\u00b2|sqm|kg|grams?|"
    r"litres?|liters?|ltrs?|bags?|packs?|rolls?|bundles?|pieces?|sets?|pairs?|"
    r"boxes?|cartons?|sheets?|points?|hours?|hrs?|days?|weeks?|months?|persons?|"
    r"pax|workers?|guards?|sessions?|copies?)\b",
    re.I,
)

REF_RE = re.compile(
    r"\b(?:quote|quotation|quot|invoice|inv|ref|reference|po|order|job|project|"
    r"phase|lot|no|number|item|code)[\s#:.\-]*[A-Z0-9][A-Z0-9/_\-]{1,}\b",
    re.I,
)

CURRENCY_SYMBOLS = {
    "$": "USD", "£": "GBP", "€": "EUR", "₦": "NGN",
    "₹": "INR", "¥": "JPY", "₽": "RUB",
}

CURRENCY_CODES = {
    "USD", "GBP", "EUR", "NGN", "INR", "JPY", "RUB", "ZAR", "KES", "GHS",
    "CAD", "AUD", "CHF", "CNY", "AED", "SAR",
}

_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "million", "billion", "naira", "dollar", "dollars", "pound",
    "pounds", "euro", "euros", "kobo", "cent", "cents", "only",
}


def is_phone(text: str) -> bool:
    """True when the string reads as a telephone number.

    Called before :func:`is_money` everywhere, so a contact line can never be
    mistaken for a total.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return False
    if is_date(stripped):
        return False
    if any(sym in stripped for sym in _CURRENCY_SYMBOLS):
        return False
    if "+" in stripped:
        return bool(PHONE_RE.search(stripped))
    if not re.fullmatch(r"[\d\s()+\-./]{7,}", stripped):
        return False
    digits = re.sub(r"\D", "", stripped)
    return len(digits) >= 7


def is_date(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return False
    return bool(DATE_RE.fullmatch(stripped)) or bool(
        DATE_RE.search(stripped) and len(stripped) <= 24
    )


def is_quantity(text: str) -> bool:
    return bool(QTY_RE.search(text))


def is_reference(text: str) -> bool:
    return bool(REF_RE.search(text))


def is_money(text: str) -> bool:
    """True when the whole short string is a single monetary amount.

    Prose that merely contains figures is rejected, which is what stops a scope
    paragraph such as "supply 3 units at 2,000 each" from becoming a priced row.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return False
    if is_phone(stripped) or is_date(stripped):
        return False
    if not (MARKED_MONEY_RE.search(stripped) or BARE_MONEY_RE.search(stripped)):
        return False
    residue = MARKED_MONEY_RE.sub("", stripped)
    residue = BARE_MONEY_RE.sub("", residue)
    residue = re.sub(r"[\s.,:;\-()/%]", "", residue)
    residue = re.sub(r"[" + re.escape(_CURRENCY_SYMBOLS) + r"]", "", residue)
    residue = re.sub(r"\b[A-Z]{3}\b", "", residue)
    return len(residue) <= 2


def is_amount_in_words(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 6:
        return False
    words = re.findall(r"[A-Za-z]+", stripped)
    if not words:
        return False
    hits = sum(1 for w in words if w.lower() in _NUMBER_WORDS)
    return hits >= max(2, len(words) // 3)


def currency_of(text: str) -> str:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    return ""


def parse_amount(text: str) -> float | None:
    """Numeric value of a monetary string, or ``None``.

    Only a string :func:`is_money` accepts is parsed, so a stray reference
    number can never enter the totals.
    """
    if not is_money(text):
        return None
    match = MARKED_MONEY_RE.search(text) or BARE_MONEY_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"[^\d.]", "", match.group(0))
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def extract_amount(text: str) -> tuple[float | None, str]:
    """Pull the first monetary figure out of a longer string.

    Used for AI-supplied financial blocks, whose text reads like "Total is
    850,000 naira." rather than a bare number. Only a figure carrying a currency
    mark, a thousands separator or two decimal places counts, so reference
    numbers and quantities are still ignored.
    """
    stripped = (text or "").strip()
    if not stripped or is_phone(stripped) or is_date(stripped):
        return None, ""
    match = MARKED_MONEY_RE.search(stripped) or BARE_MONEY_RE.search(stripped)
    if not match:
        return None, ""
    digits = re.sub(r"[^\d.]", "", match.group(0))
    if not digits:
        return None, ""
    try:
        return float(digits), match.group(0).strip()
    except ValueError:
        return None, ""


def looks_numeric(text: str) -> bool:
    return bool(re.fullmatch(r"[\d.,\s%]+", text.strip()))
