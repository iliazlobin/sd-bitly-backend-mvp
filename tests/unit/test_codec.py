"""Unit tests for base62 codec — pure functions, no external dependencies."""

import pytest

from src.bitly.services.codec import base62_decode, base62_encode


class TestBase62Encode:
    def test_zero(self) -> None:
        assert base62_encode(0) == "0000000"

    def test_one(self) -> None:
        assert base62_encode(1) == "0000001"

    def test_61_is_Z(self) -> None:
        # 61 is the last char in the alphabet ('Z')
        assert base62_encode(61) == "000000Z"

    def test_62_is_10(self) -> None:
        # 62 = 1*62 + 0 → "10" (base62), padded to "0000010"
        assert base62_encode(62) == "0000010"

    def test_3844_is_100(self) -> None:
        # 62^2 = 3844 → "100" padded to "0000100"
        assert base62_encode(3844) == "0000100"

    def test_padding(self) -> None:
        # All values < 62^6 should produce exactly 7 chars with leading zeros.
        assert base62_encode(62**5 - 1) == "00ZZZZZ"
        assert len(base62_encode(62**5 - 1)) == 7

    def test_62_to_6_minus_1(self) -> None:
        # 62^6 - 1 = 56,800,235,583 → "ZZZZZZ" padded to 7
        val = 62**6 - 1
        encoded = base62_encode(val)
        assert encoded == "0ZZZZZZ"
        assert len(encoded) == 7

    def test_62_to_6(self) -> None:
        # 62^6 = 56,800,235,584 → "1000000" (7 chars, no padding needed)
        val = 62**6
        encoded = base62_encode(val)
        assert encoded == "1000000"
        assert len(encoded) == 7

    def test_62_to_7_minus_1(self) -> None:
        # 62^7 - 1 = 3,521,614,606,207 → "ZZZZZZZ"
        val = 62**7 - 1
        encoded = base62_encode(val)
        assert encoded == "ZZZZZZZ"
        assert len(encoded) == 7


class TestBase62Decode:
    def test_zero(self) -> None:
        assert base62_decode("0000000") == 0

    def test_one(self) -> None:
        assert base62_decode("0000001") == 1

    def test_Z(self) -> None:
        assert base62_decode("000000Z") == 61

    def test_10(self) -> None:
        assert base62_decode("0000010") == 62

    def test_100(self) -> None:
        assert base62_decode("0000100") == 3844

    def test_ZZZZZZ(self) -> None:
        assert base62_decode("0ZZZZZZ") == 62**6 - 1

    def test_1000000(self) -> None:
        assert base62_decode("1000000") == 62**6

    def test_ZZZZZZZ(self) -> None:
        assert base62_decode("ZZZZZZZ") == 62**7 - 1


class TestRoundtrip:
    """Encode → decode should return the original value."""

    @pytest.mark.parametrize("n", [
        0, 1, 10, 61, 62, 100, 1000, 9999,
        62**6 - 1, 62**6, 62**6 + 1,
        62**7 - 1,
    ])
    def test_roundtrip(self, n: int) -> None:
        encoded = base62_encode(n)
        assert len(encoded) == 7, f"encode({n}) = {encoded!r}, expected 7 chars"
        assert base62_decode(encoded) == n, f"decode(encode({n})) != {n}"
