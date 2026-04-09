
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

def detect_columns(headers: list[str]) -> dict[str, int | None]:

    n = len(headers)
    
    empty: dict[str, int | None] = {"date": None, "merchant": None, "amount": None}
    
    if n == 0:
        return empty.copy()
    per_col: list[tuple[float, float, float]] = []
    for h in headers:
        per_col.append(
            (
                _score_header_for_role(h, _DATE_KEYWORDS),
                _score_header_for_role(h, _MERCHANT_KEYWORDS),
                _score_header_for_role(h, _AMOUNT_KEYWORDS),
            )
        )

    if n >= 3:
        best_total = -1.0
        best_mapping = empty.copy()
        for cols in itertools.permutations(range(n), 3):
            d, m, a = cols
            total = per_col[d][0] + per_col[m][1] + per_col[a][2]
            if total > best_total:
                best_total = total
                best_mapping = {"date": d, "merchant": m, "amount": a}
        if best_total <= 0.0:
            return empty.copy()
        role_order = ("date", "merchant", "amount")
        for key in role_order:
            idx = best_mapping[key]
            if idx is None:
                continue
            role_idx = role_order.index(key)
            if per_col[idx][role_idx] < _MIN_ROLE_SCORE:
                best_mapping[key] = None
        return best_mapping

    used: set[int] = set()
    result = empty.copy()
    role_keys = ("date", "merchant", "amount")
    for role_idx, key in enumerate(role_keys):
        best_i: int | None = None
        best_s = -1.0
        for i in range(n):
            if i in used:
                continue
            s = per_col[i][role_idx]
            if s > best_s:
                best_s = s
                best_i = i
        if best_i is not None and best_s >= _MIN_ROLE_SCORE:
            result[key] = best_i
            used.add(best_i)
    return result