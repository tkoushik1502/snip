import pytest

from app.ratelimit import TokenBucketLimiter
from app.shortcode import ALPHABET, decode, encode, is_valid_alias, random_code


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.parametrize("n", [0, 1, 61, 62, 3843, 3844, 10**12])
def test_base62_roundtrip(n):
    assert decode(encode(n)) == n


def test_base62_known_values():
    assert encode(0) == "0"
    assert encode(61) == "Z"
    assert encode(62) == "10"


def test_random_code_shape():
    code = random_code(7)
    assert len(code) == 7
    assert all(ch in ALPHABET for ch in code)


def test_alias_validation():
    assert is_valid_alias("my-link_2")
    assert not is_valid_alias("API")  # reserved, case-insensitively
    assert not is_valid_alias("no")


def test_bucket_allows_burst_then_blocks():
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=3, refill_per_sec=1, clock=clock)
    assert [limiter.allow("ip")[0] for _ in range(4)] == [True, True, True, False]


def test_bucket_refills_over_time():
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=2, refill_per_sec=0.5, clock=clock)
    limiter.allow("ip")
    limiter.allow("ip")
    allowed, retry_after = limiter.allow("ip")
    assert not allowed
    assert retry_after == pytest.approx(2.0)

    clock.now = 2.0  # one token's worth of refill
    assert limiter.allow("ip")[0]
    assert not limiter.allow("ip")[0]


def test_bucket_never_exceeds_capacity():
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=2, refill_per_sec=1, clock=clock)
    clock.now = 1000.0  # long idle must not bank 1000 tokens
    assert [limiter.allow("ip")[0] for _ in range(3)] == [True, True, False]


def test_buckets_are_per_key():
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=1, refill_per_sec=1, clock=clock)
    assert limiter.allow("a")[0]
    assert not limiter.allow("a")[0]
    assert limiter.allow("b")[0]
