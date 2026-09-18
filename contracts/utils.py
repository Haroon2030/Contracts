from decimal import Decimal, InvalidOperation


_ONES = ["", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
_TEENS = [
    "عشرة",
    "أحد عشر",
    "اثنا عشر",
    "ثلاثة عشر",
    "أربعة عشر",
    "خمسة عشر",
    "ستة عشر",
    "سبعة عشر",
    "ثمانية عشر",
    "تسعة عشر",
]
_TENS = ["", "عشرة", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
_HUNDREDS = [
    "",
    "مائة",
    "مائتان",
    "ثلاثمائة",
    "أربعمائة",
    "خمسمائة",
    "ستمائة",
    "سبعمائة",
    "ثمانمائة",
    "تسعمائة",
]


def _join(*parts):
    return " و ".join(p for p in parts if p)


def _under_hundred(n):
    if n <= 0:
        return ""
    if n < 10:
        return _ONES[n]
    if n < 20:
        return _TEENS[n - 10]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS[tens]
    return f"{_ONES[ones]} و{_TENS[tens]}"


def _under_thousand(n):
    if n <= 0:
        return ""
    hundreds, rest = divmod(n, 100)
    return _join(_HUNDREDS[hundreds], _under_hundred(rest))


def _scale(n, singular, dual, plural, accusative):
    if n <= 0:
        return ""
    if n == 1:
        return singular
    if n == 2:
        return dual
    words = _under_thousand(n)
    if 3 <= n <= 10:
        return f"{words} {plural}"
    return f"{words} {accusative}"


def amount_to_arabic_words(value):
    """تحويل المبلغ إلى صياغة عربية مناسبة للوثائق الرسمية."""
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    riyals = int(amount)
    halalas = int((amount - riyals) * 100)
    if riyals == 0 and halalas == 0:
        return "صفر ريال سعودي"

    millions, rest = divmod(riyals, 1_000_000)
    thousands, units = divmod(rest, 1000)
    parts = [
        _scale(millions, "مليون", "مليونان", "ملايين", "مليوناً"),
        _scale(thousands, "ألف", "ألفان", "آلاف", "ألفاً"),
        _under_thousand(units),
    ]
    words = _join(*parts)
    if riyals == 1:
        result = "ريال سعودي واحد"
    elif riyals == 2:
        result = "ريالان سعوديان"
    elif riyals:
        result = f"{words} ريال سعودي"
    else:
        result = ""
    if halalas:
        halala_words = _under_hundred(halalas)
        result = _join(result, f"{halala_words} هللة") if result else f"{halala_words} هللة"
    return result
