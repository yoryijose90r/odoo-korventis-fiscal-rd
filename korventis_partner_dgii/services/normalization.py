import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_IDENTIFICATION_SEPARATORS = re.compile(r"[\s-]+")


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


def normalize_identification(value):
    return _IDENTIFICATION_SEPARATORS.sub("", (value or "").strip())


def has_unsafe_control_characters(value):
    return any(
        unicodedata.category(character) in {"Cc", "Cf"}
        and character not in "\t\r\n"
        for character in value or ""
    )


def escape_like(value):
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
