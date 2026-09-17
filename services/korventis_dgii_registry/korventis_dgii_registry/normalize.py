"""Safe string normalization. RNC stays text; leading zeros are kept."""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalize_name(value):
    value = _WHITESPACE.sub(" ", (value or "").strip())
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
        and unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return _WHITESPACE.sub(" ", without_marks).upper()


def has_unsafe_control_characters(value):
    return any(
        unicodedata.category(character) in {"Cc", "Cf"}
        and character not in "\t\r\n"
        for character in value or ""
    )


def normalize_header(value):
    text = unicodedata.normalize("NFC", (value or "").replace("\ufeff", "").strip())
    return _WHITESPACE.sub(" ", text).upper()
