# -*- coding: utf-8 -*-
"""
ابزار تقویم شمسی (جلالی) بدون نیاز به پکیج خارجی و تبدیل ارقام فارسی.
پشتیبانی از منطقه زمانی تهران (Asia/Tehran) و محاسبه هوشمند بازه برنامه مطالعاتی.
"""

from __future__ import annotations
import datetime
from zoneinfo import ZoneInfo

PERSIAN_MONTHS = [
    "",
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

# Python weekday(): Monday=0 ... Sunday=6
PERSIAN_WEEKDAYS = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}

_EN_TO_FA_MAP = str.maketrans("0123456789٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹")
_FA_TO_EN_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_persian_digits(value: str | int | float) -> str:
    """تبدیل تمام اعداد انگلیسی و عربی موجود در رشته به اعداد فارسی."""
    return str(value).translate(_EN_TO_FA_MAP)


def to_english_digits(value: str) -> str:
    """تبدیل اعداد فارسی و عربی به انگلیسی برای محاسبات ریاضی."""
    return str(value).translate(_FA_TO_EN_MAP)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل دقیق تاریخ میلادی به شمسی (جلالی)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + int((gy2 + 3) / 4)
        - int((gy2 + 99) / 100)
        + int((gy2 + 399) / 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * int(days / 12053)
    days %= 12053
    jy += 4 * int(days / 1461)
    days %= 1461
    if days > 365:
        jy += int((days - 1) / 365)
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + int(days / 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + int((days - 186) / 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل دقیق تاریخ شمسی (جلالی) به میلادی."""
    jy += 1595
    days = -355668 + (365 * jy) + (int(jy / 33) * 8) + int(((jy % 33) + 3) / 4) + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy = 400 * int(days / 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * int(days / 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * int(days / 1461)
    days %= 1461
    if days > 365:
        gy += int((days - 1) / 365)
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [
        0,
        31,
        29 if ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def get_tehran_today() -> datetime.date:
    """دریافت تاریخ امروز به وقت تهران."""
    now_tehran = datetime.datetime.now(ZoneInfo("Asia/Tehran"))
    return now_tehran.date()


def get_persian_weekday(d: datetime.date) -> str:
    """نام روز هفته به فارسی."""
    return PERSIAN_WEEKDAYS[d.weekday()]


def format_jalali_date(
    d: datetime.date, include_weekday: bool = True, include_year: bool = False
) -> str:
    """فرمت کردن تاریخ شمسی به صورت «دوشنبه ۴ آبان» یا «دوشنبه ۴ آبان ۱۴۰۵»."""
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    month_name = PERSIAN_MONTHS[jm]
    parts = []
    if include_weekday:
        parts.append(get_persian_weekday(d))
    parts.append(to_persian_digits(jd))
    parts.append(month_name)
    if include_year:
        parts.append(to_persian_digits(jy))
    return " ".join(parts)


def get_next_saturday(from_date: datetime.date) -> datetime.date:
    """پیدا کردن تاریخ شنبه آینده نسبت به تاریخ ورودی."""
    # Saturday is weekday() == 5
    days_ahead = (5 - from_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_date + datetime.timedelta(days=days_ahead)


def compute_plan_date_range(start_date: datetime.date, num_days: int) -> dict:
    """
    محاسبه کامل بازه تاریخی برنامه بر اساس تاریخ شروع و تعداد روزها.
    خروجی شامل متن کوتاه سربرگ، متن کاور، و لیست تاریخ‌های روز به روز است.
    """
    n = max(1, num_days)
    end_date = start_date + datetime.timedelta(days=n - 1)
    jy1, jm1, jd1 = gregorian_to_jalali(start_date.year, start_date.month, start_date.day)
    jy2, jm2, jd2 = gregorian_to_jalali(end_date.year, end_date.month, end_date.day)

    start_full = format_jalali_date(start_date, include_weekday=True, include_year=False)
    end_full = format_jalali_date(end_date, include_weekday=True, include_year=False)

    if jm1 == jm2:
        short_range = f"{to_persian_digits(jd1)} تا {to_persian_digits(jd2)} {PERSIAN_MONTHS[jm1]} {to_persian_digits(jy1)}"
    else:
        short_range = (
            f"{to_persian_digits(jd1)} {PERSIAN_MONTHS[jm1]} تا "
            f"{to_persian_digits(jd2)} {PERSIAN_MONTHS[jm2]} {to_persian_digits(jy2)}"
        )

    cover_subtitle = f"شروع برنامه: {start_full} تا {end_full} | برنامه {to_persian_digits(n)} روزه"
    header_date_text = f"تاریخ: {short_range}"

    daily_dates = []
    for i in range(n):
        cur = start_date + datetime.timedelta(days=i)
        daily_dates.append(
            {
                "date": cur,
                "weekday": get_persian_weekday(cur),
                "short_date": format_jalali_date(cur, include_weekday=False, include_year=False),
                "full_label": format_jalali_date(cur, include_weekday=True, include_year=False),
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "num_days": n,
        "short_range": short_range,
        "header_date_text": header_date_text,
        "cover_subtitle": cover_subtitle,
        "start_full": start_full,
        "end_full": end_full,
        "daily_dates": daily_dates,
        "file_date_slug": f"{jy1}-{jm1:02d}-{jd1:02d}",
    }
