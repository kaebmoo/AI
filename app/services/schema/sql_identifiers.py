import re


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_safe_identifier(value: str) -> bool:
    return bool(value) and bool(_SAFE_IDENTIFIER_RE.fullmatch(value))


def assert_safe_identifier(value: str, label: str) -> str:
    if not is_safe_identifier(value):
        raise ValueError(f"Invalid {label}")
    return value


def quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("Invalid SQL identifier")
    return '"' + value.replace('"', '""') + '"'