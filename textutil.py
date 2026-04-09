from __future__ import annotations

def clean_text(text: str) -> str:
    parts: list[str] = []
    for char in (text or "").lower():
        if char.isalnum():
            parts.append(char)
        else:
            parts.append(" ")
    return " ".join("".join(parts).split())    

