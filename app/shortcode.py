import re
import secrets

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)

# Paths the app itself serves; a custom alias must never shadow them.
RESERVED = frozenset({"api", "static", "docs", "redoc", "openapi.json", "health"})
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


def encode(n: int) -> str:
    """Encode a non-negative integer in base62."""
    if n < 0:
        raise ValueError("cannot encode negative numbers")
    if n == 0:
        return ALPHABET[0]
    digits = []
    while n:
        n, rem = divmod(n, BASE)
        digits.append(ALPHABET[rem])
    return "".join(reversed(digits))


def decode(s: str) -> int:
    n = 0
    for ch in s:
        n = n * BASE + ALPHABET.index(ch)
    return n


def random_code(length: int = 7) -> str:
    """A random base62 code.

    Random rather than sequential so codes can't be enumerated to discover
    other people's links. 62^7 ≈ 3.5 trillion codes, so collisions are rare,
    and the caller retries on the database's unique constraint when one happens.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS_PATTERN.match(alias)) and alias.lower() not in RESERVED
