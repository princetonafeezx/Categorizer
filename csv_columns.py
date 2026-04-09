
from __future__ import annotations

import itertools

from textutil import clean_text

_MIN_KEYWORD_SUBSTRING_LEN = 5
_MIN_ROLE_SCORE = 0.4

_DATE_KEYWORDS = (
    "date",
    "posted",
    "day",
)
_MERCHANT_KEYWORDS = (
    "merchant",
    "description",
    "payee",
    "narrative",
    "memo",
    "details",
    "detail",
    "vendor",
    "counterparty",
)
_AMOUNT_KEYWORDS = (
    "amount",
    "debit",
    "credit",
    "value",
    "total",
    "price",
)

def _score_header_for_role(header: str, keywords: tuple[str, ...]) -> float:
    h = clean_text(header)
    if not h:
        return 0.0
    tokens = h.split()
    best = 0.0
    for kw in keywords:
        if h == kw:
            best = max(best, 1.0)
        elif kw in tokens:
            best = max(best, 0.95)
        elif h.startswith(kw + " ") or h.endswith(" " + kw):
            best = max(best, 0.9)
        elif len(kw) >= _MIN_KEYWORD_SUBSTRING_LEN and kw in h:
            best = max(best, 0.75)
    return best
