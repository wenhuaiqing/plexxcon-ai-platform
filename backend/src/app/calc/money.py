"""Integer arithmetic for money and quantities. No float decides anything, so
the build is byte-identical on every platform and the browser's preview can be
checked against the server to the cent."""

from __future__ import annotations


def rhu(numerator: int, denominator: int) -> int:
    """Round half up, for non-negative operands."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    if numerator < 0:
        return -rhu(-numerator, denominator)
    return (2 * numerator + denominator) // (2 * denominator)


def ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def to_cents(value) -> int:
    """Dollars as entered (number or string) to integer cents."""
    if value is None or value == "":
        return 0
    text = str(value).replace(",", "").replace("$", "").strip()
    negative = text.startswith("-")
    text = text.lstrip("+-")
    whole, _, frac = text.partition(".")
    if not (whole or frac) or not (whole or "0").isdigit() or not (frac or "0").isdigit():
        raise ValueError(f"not an amount: {value!r}")
    frac = (frac + "000")[:3]
    cents = int(whole or "0") * 100 + int(frac[:2]) + (1 if int(frac[2]) >= 5 else 0)
    return -cents if negative else cents


def to_scaled(value, scale: int) -> int:
    """A decimal as entered to an integer at the given scale (100 = two places)."""
    if value is None or value == "":
        return 0
    text = str(value).replace(",", "").strip()
    negative = text.startswith("-")
    text = text.lstrip("+-")
    whole, _, frac = text.partition(".")
    if not (whole or frac) or not (whole or "0").isdigit() or not (frac or "0").isdigit():
        raise ValueError(f"not a number: {value!r}")
    digits = len(str(scale)) - 1
    frac = (frac + "0" * (digits + 1))[: digits + 1]
    scaled = int(whole or "0") * scale + int(frac[:digits] or "0") + (1 if int(frac[digits]) >= 5 else 0)
    return -scaled if negative else scaled
