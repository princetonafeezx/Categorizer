from __future__ import annotations

def clean_text(text: str) -> str:
    parts: list[str] = []
    for char in (text or "").lower():
        if char.isalnum():
            parts.append(char)
        else:
            parts.append(" ")
    return " ".join("".join(parts).split())    

def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous_row = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current_row = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insert_cost = current_row[right_index - 1] + 1
            delete_cost = previous_row[right_index] + 1
            replace_cost = previous_row[right_index - 1] + (0 if left_char == right_char else 1)
            current_row.append(min(insert_cost, delete_cost, replace_cost))
        previous_row = current_row
    return previous_row[-1]

def similarity_ratio(left: str, right: str) -> float:
    left = clean_text(left)
    right = clean_text(right)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        shorter = min(len(left), len(right))
        longer = max(len(left), len(right))
        return shorter / longer
    distance = _levenshtein_distance(left, right)
    largest = max(len(left), len(right))
    return max(0.0, 1.0 - (distance / largest))