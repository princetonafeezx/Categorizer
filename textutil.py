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