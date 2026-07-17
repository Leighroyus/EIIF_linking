from __future__ import annotations

from datetime import datetime


LAST_NAME_MAP = {
    "A": "0", "E": "0",
    "B": "1",
    "F": "2", "P": "2",
    "C": "3", "K": "3", "Q": "3",
    "D": "4", "T": "4",
    "G": "5", "J": "5",
    "H": "6",
    "I": "7", "Y": "7",
    "L": "8",
    "M": "9", "N": "9",
    "S": "A", "X": "A",
    "Z": "B",
    "R": "C",
    "O": "D", "U": "D",
    "V": "E", "W": "E",
}

FIRST_NAME_MAP = {
    "A": "0",
    "B": "1", "P": "1",
    "C": "2", "S": "2",
    "X": "3", "Z": "3",
    "D": "4", "T": "4",
    "G": "5",
    "K": "6", "Q": "6",
    "E": "7", "I": "7", "Y": "7",
    "J": "8",
    "F": "9", "V": "9",
    "H": "A",
    "L": "B",
    "M": "C",
    "N": "D",
    "O": "E",
    "U": "F", "W": "F",
    "R": "G",
}

GENDER_MAP = {"M": "1", "F": "2", "C": "9", "U": "9"}


def _normalise_name(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("'", "").replace(" ", "").upper()


def _collapse_duplicates(value: str, start_index: int) -> str:
    if not value:
        return value
    chars = list(value)
    i = max(start_index, 1)
    while i < len(chars) - 1:
        if chars[i] == chars[i + 1] and chars[i] in set("0123456789ABCDEFG"):
            del chars[i + 1]
        else:
            i += 1
    return "".join(chars)


def _format_dob(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("-", "")
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned
    try:
        return datetime.fromisoformat(value).strftime("%Y%m%d")
    except ValueError:
        return ""


def build_slk(
    first_name: str | None,
    last_name: str | None,
    dob: str | None,
    gender: str | None,
) -> str | None:
    first_name_clean = _normalise_name(first_name)
    last_name_clean = _normalise_name(last_name)

    parts: list[str] = []
    if last_name_clean:
        parts.append(last_name_clean[0])
        parts.extend(LAST_NAME_MAP.get(char, "") for char in last_name_clean[1:])

    slk = "".join(parts)
    slk = _collapse_duplicates(slk, 1)

    if first_name_clean:
        slk = f"{slk}{first_name_clean[0]}"
        first_name_start = len(slk)
        slk = f"{slk}{''.join(FIRST_NAME_MAP.get(char, '') for char in first_name_clean[1:])}"
        slk = _collapse_duplicates(slk, first_name_start)

    slk = f"{slk}{_format_dob(dob)}{GENDER_MAP.get((gender or '').upper(), '')}"
    return slk or None
