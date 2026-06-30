"""Base62 encoding and decoding for short code generation.

Uses the character set 0-9a-zA-Z (62 symbols). Encoded codes are always
exactly 7 characters, left-padded with '0'.
"""

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Precomputed lookup for O(1) decode per character.
_CHAR_TO_VALUE: dict[str, int] = {c: i for i, c in enumerate(ALPHABET)}

CODE_LENGTH = 7


def base62_encode(n: int) -> str:
    """Encode an integer to a 7-character base62 string, left-padded with '0'."""
    if n == 0:
        return "0".rjust(CODE_LENGTH, "0")

    chars: list[str] = []
    while n > 0:
        chars.append(ALPHABET[n % 62])
        n //= 62
    return "".join(reversed(chars)).rjust(CODE_LENGTH, "0")


def base62_decode(s: str) -> int:
    """Decode a base62 string back to an integer.

    Leading zeros are stripped before decoding, so '0000001' decodes to 1
    and '0000000' decodes to 0.
    """
    stripped = s.lstrip("0") or "0"
    n = 0
    for c in stripped:
        n = n * 62 + _CHAR_TO_VALUE[c]
    return n
