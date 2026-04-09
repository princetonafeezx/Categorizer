
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


