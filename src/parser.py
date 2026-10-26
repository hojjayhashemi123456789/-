# -*- coding: utf-8 -*-
"""
پارس هوشمند خروجی برنامه‌های مطالعاتی جمینای (پشتیبانی از Markdown Tables، Tab-separated و متن کپی‌شده از وب)
به همراه:
- محاسبه وزن عرض ستون‌ها مطابق ماکروی VBA AutoFormatStudyTables
- گرد کردن تعداد تست‌ها به مضرب ۱۰ (۱۰، ۲۰، ۳۰، ...)
- استخراج آمار کامل برای اینفوگرافیک «وضعیت هفتگی» (تفکیک آموزش/تسلط/مرور، روند ساعت روزانه، و مباحث هر درس)
"""

from __future__ import annotations
import math
import re
from src.jalali import to_persian_digits, to_english_digits

DEFAULT_HEADERS = [
    "پارت",
    "درس",
    "مبحث",
    "نوع پارت",
    "مدت زمان",
    "تعداد تست",
    "بازه مطالعه",
]

ORDINAL_DAYS = [
    "اول",
    "دوم",
    "سوم",
    "چهارم",
    "پنجم",
    "ششم",
    "هفتم",
    "هشتم",
    "نهم",
    "دهم",
    "یازدهم",
    "دوازدهم",
    "سیزدهم",
    "چهاردهم",
]


def round_to_nearest_10(value: int | float) -> int:
    """
    گرد کردن اعداد تست به نزدیک‌ترین مضرب ۱۰ (مثلاً ۱۴ -> ۱۰، ۱۶ -> ۲۰، ۸۵ -> ۹۰).
    اگر عدد بزرگ‌تر از ۰ ولی کمتر از ۵ باشد، ۱۰ برمی‌گرداند تا صفر نشود.
    """
    if value <= 0:
        return 0
    rounded = int(math.floor((value + 5) / 10.0) * 10)
    return max(10, rounded)


def format_hours_clean(minutes: int | float) -> str:
    """تبدیل دقیقه به رشته ساعت تمیز بدون دقیقه اضافی (مثلاً 990 دقیقه -> ۱۶.۵)."""
    hrs = round(minutes / 60.0, 2)
    s = f"{hrs:.2f}".rstrip("0").rstrip(".")
    return to_persian_digits(s)


def format_doctor_student_title(raw_name: str) -> str:
    """
    فرمت کردن هوشمند نام دانش‌آموز برای سربرگ به صورت «برنامه دکتر [نام]».
    مثال:
    - «نرگس» -> «برنامه دکتر نرگس»
    - «خانم علیپور» -> «برنامه دکتر خانم علیپور»
    - «دکتر نرگس» -> «برنامه دکتر نرگس»
    """
    clean = raw_name.strip()
    if not clean:
        return "برنامه دکتر"
    if clean.startswith("برنامه دکتر"):
        return to_persian_digits(clean)
    if clean.startswith("دکتر "):
        return to_persian_digits(f"برنامه {clean}")
    return to_persian_digits(f"برنامه دکتر {clean}")


def compute_column_weights(headers: list[str]) -> list[float]:
    """
    محاسبه دقیق وزن هر ستون بر اساس عنوان ستون (مطابق منطق ماکروی VBA کاربر):
    - مبحث / توضیحات: 3.6
    - درس: 2.0
    - نوع پارت: 1.8
    - مدت زمان: 1.5
    - تعداد تست: 1.3
    - بازه مطالعه: 1.1
    - پارت / ردیف / شماره: 0.9
    """
    weights: list[float] = []
    for h in headers:
        txt = h.strip()
        if any(k in txt for k in ["مبحث", "توضیح", "فصل", "گفتار", "جزئیات"]):
            weights.append(3.6)
        elif "نوع" in txt:
            weights.append(1.8)
        elif any(k in txt for k in ["مدت", "زمان"]):
            weights.append(1.5)
        elif "تست" in txt:
            weights.append(1.3)
        elif "بازه" in txt or "نوبت" in txt or "شیفت" in txt:
            weights.append(1.1)
        elif txt in ("پارت", "ردیف", "شماره") or txt.startswith("پارت"):
            weights.append(0.9)
        elif "درس" in txt:
            weights.append(2.0)
        else:
            weights.append(2.0)
    return weights


def compute_column_percentages(headers: list[str]) -> list[float]:
    """تبدیل وزن ستون‌ها به درصد (مجموع ۱۰۰٪)."""
    weights = compute_column_weights(headers)
    total = sum(weights) or 1.0
    return [round((w / total) * 100.0, 2) for w in weights]


def _is_separator_line(line: str) -> bool:
    """تشخیص خط جداکننده جدول مارک‌داون مانند |---|---|."""
    cleaned = line.strip().replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
    return len(cleaned) == 0 and ("-" in line)


def _split_table_row(line: str) -> list[str] | None:
    """تبدیل یک خط جدول (Pipe یا Tab) به لیست سلول‌ها."""
    s = line.strip()
    if not s:
        return None
    if "|" in s:
        if _is_separator_line(s):
            return []
        parts = [c.strip() for c in s.strip("|").split("|")]
        if len(parts) >= 2:
            return parts
    if "\t" in s:
        parts = [c.strip() for c in s.split("\t")]
        if len(parts) >= 3:
            return parts
    multi_space = [c.strip() for c in re.split(r"\s{2,}", s) if c.strip()]
    if len(multi_space) >= 4:
        return multi_space
    return None


def _is_header_row(cells: list[str]) -> bool:
    """تشخیص اینکه آیا این سطر، سطر عنوان ستون‌هاست یا خیر."""
    joined = " ".join(cells)
    keywords = ["پارت", "درس", "مبحث", "مدت زمان", "تعداد تست", "بازه مطالعه", "نوع پارت"]
    matches = sum(1 for k in keywords if k in joined)
    return matches >= 2


def _normalize_decimal_str(s: str) -> str:
    """تبدیل اعداد فارسی و ممیزهای فارسی (مثل ۶/۵ یا 7,25) به فرمت استاندارد 6.5."""
    en = to_english_digits(s)
    en = re.sub(r"(?<=\d)[/،,٫](?=\d)", ".", en)
    return en


def _extract_minutes(duration_str: str) -> int:
    """استخراج مدت زمان به دقیقه از عباراتی مانند «90 دقیقه» یا «1.5 ساعت» یا «۱/۵ ساعت»."""
    en = _normalize_decimal_str(duration_str)
    nums = re.findall(r"\d+(?:\.\d+)?", en)
    if not nums:
        return 0
    val = float(nums[0])
    if "ساعت" in en and "دقیقه" not in en:
        return int(round(val * 60))
    return int(round(val))


def _extract_tests(test_str: str) -> int:
    """استخراج تعداد تست از سلول تعداد تست."""
    en = _normalize_decimal_str(test_str)
    nums = re.findall(r"\d+", en)
    if not nums:
        return 0
    return int(nums[0])


def _classify_part_type(type_str: str) -> str:
    """دسته‌بندی نوع پارت به یکی از ۳ دسته: آموزش، تسلط، مرور."""
    t = type_str.strip()
    if "آموزش" in t or "درسنامه" in t or "یادگیری" in t:
        return "آموزش"
    if "تسلط" in t or "تست" in t or "تمرین" in t:
        return "تسلط"
    if "مرور" in t or "جمع‌بندی" in t or "جمعبندی" in t or "خلاصه" in t:
        return "مرور"
    return "آموزش"


def parse_study_plan(raw_text: str) -> dict:
    """
    پارس کردن متن کامل خروجی جمینای و استخراج روزها، ساعت شروع، جداول، جمع ساعت مطالعه
    و خلاصه آماری کامل برای هر دو فایل PDF (برنامه مطالعاتی + وضعیت هفتگی).
    """
    lines = [ln.strip() for ln in raw_text.splitlines()]
    days: list[dict] = []

    current_day: dict | None = None
    day_title_pattern = re.compile(
        r"^(?:#+\s*|\*\*|\*)?(?:📅\s*)?(روز\s+\S+.*?)(?:\*\*|\*)?$"
    )
    start_time_pattern = re.compile(r"ساعت\s*شروع\s*[:：]?\s*(.+)$")
    total_hours_pattern = re.compile(r"(جمع\s*ساعت\s*مطالعه\s*[:：]?\s*.+)$")

    def ensure_current_day(default_idx: int) -> dict:
        nonlocal current_day
        if current_day is None:
            ord_name = (
                ORDINAL_DAYS[default_idx]
                if default_idx < len(ORDINAL_DAYS)
                else to_persian_digits(default_idx + 1)
            )
            current_day = {
                "title": f"روز {ord_name}",
                "start_time": "۸:۰۰",
                "headers": list(DEFAULT_HEADERS),
                "rows": [],
                "total_hours": "",
            }
        return current_day

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # ۱. بررسی جمع ساعت مطالعه
        m_tot = total_hours_pattern.search(line.replace("*", ""))
        if m_tot:
            if current_day is not None and current_day["rows"]:
                current_day["total_hours"] = to_persian_digits(m_tot.group(1).strip())
                days.append(current_day)
                current_day = None
            i += 1
            continue

        # ۲. بررسی شروع یک روز جدید
        clean_line = line.replace("*", "").replace("#", "").strip()
        m_day = day_title_pattern.match(clean_line)
        if m_day and ("پارت" not in clean_line) and ("|" not in line) and ("\t" not in line):
            if current_day is not None and current_day["rows"]:
                days.append(current_day)
            current_day = {
                "title": to_persian_digits(m_day.group(1).strip()),
                "start_time": "",
                "headers": list(DEFAULT_HEADERS),
                "rows": [],
                "total_hours": "",
            }
            i += 1
            continue

        # ۳. بررسی ساعت شروع
        m_start = start_time_pattern.search(clean_line)
        if m_start and ("|" not in line):
            day_obj = ensure_current_day(len(days))
            day_obj["start_time"] = to_persian_digits(m_start.group(1).strip())
            i += 1
            continue

        # ۴. بررسی سطر جدول
        cells = _split_table_row(line)
        if cells is not None:
            if len(cells) == 0:
                i += 1
                continue
            day_obj = ensure_current_day(len(days))
            if _is_header_row(cells):
                if cells[-1].strip() == "پارت" and cells[0].strip() != "پارت":
                    cells = list(reversed(cells))
                    day_obj["_reversed_cols"] = True
                else:
                    day_obj["_reversed_cols"] = False
                day_obj["headers"] = [to_persian_digits(c) for c in cells]
            else:
                if day_obj.get("_reversed_cols", False):
                    cells = list(reversed(cells))
                hdr_len = len(day_obj["headers"])
                if len(cells) < hdr_len:
                    cells = cells + ["-"] * (hdr_len - len(cells))
                elif len(cells) > hdr_len:
                    cells = cells[:hdr_len]
                day_obj["rows"].append([to_persian_digits(c) for c in cells])
            i += 1
            continue

        i += 1

    if current_day is not None and current_day["rows"]:
        days.append(current_day)

    # محاسبات آماری دقیق برای جدول انتهایی و اینفوگرافیک وضعیت هفتگی
    total_week_minutes = 0
    total_week_tests_raw = 0
    total_parts_count = 0

    subject_minutes: dict[str, int] = {}
    subject_tests_raw: dict[str, int] = {}
    subject_topics: dict[str, list[str]] = {}

    part_type_minutes: dict[str, int] = {"آموزش": 0, "تسلط": 0, "مرور": 0}
    part_type_counts: dict[str, int] = {"آموزش": 0, "تسلط": 0, "مرور": 0}
    daily_stats: list[dict] = []

    for d_idx, d in enumerate(days):
        headers = d["headers"]
        subj_idx = next((idx for idx, h in enumerate(headers) if "درس" in h), 1)
        topic_idx = next((idx for idx, h in enumerate(headers) if "مبحث" in h or "توضیح" in h), 2)
        type_idx = next((idx for idx, h in enumerate(headers) if "نوع" in h), 3)
        dur_idx = next((idx for idx, h in enumerate(headers) if "مدت" in h or "زمان" in h), 4)
        test_idx = next((idx for idx, h in enumerate(headers) if "تست" in h), 5)

        day_minutes = 0
        for r in d["rows"]:
            total_parts_count += 1
            mins = _extract_minutes(r[dur_idx]) if dur_idx < len(r) else 0
            tsts = _extract_tests(r[test_idx]) if test_idx < len(r) else 0
            subj = r[subj_idx].strip() if subj_idx < len(r) else "سایر"
            topic = r[topic_idx].strip() if topic_idx < len(r) else ""
            ptype_raw = r[type_idx].strip() if type_idx < len(r) else ""

            ptype = _classify_part_type(ptype_raw)
            part_type_minutes[ptype] = part_type_minutes.get(ptype, 0) + mins
            part_type_counts[ptype] = part_type_counts.get(ptype, 0) + 1

            day_minutes += mins
            total_week_minutes += mins
            total_week_tests_raw += tsts

            if subj and subj != "-":
                subject_minutes[subj] = subject_minutes.get(subj, 0) + mins
                subject_tests_raw[subj] = subject_tests_raw.get(subj, 0) + tsts
                if subj not in subject_topics:
                    subject_topics[subj] = []
                if topic and topic != "-" and topic not in subject_topics[subj]:
                    subject_topics[subj].append(topic)

        hrs = round(day_minutes / 60.0, 2)
        hrs_str = f"{hrs:.2f}".rstrip("0").rstrip(".")
        if not d.get("total_hours"):
            d["total_hours"] = to_persian_digits(f"جمع ساعت مطالعه: {hrs_str} ساعت")
        if not d.get("start_time"):
            d["start_time"] = "۸:۱۵"
        d["day_hours"] = hrs
        d["day_minutes"] = day_minutes
        d.pop("_reversed_cols", None)

        # استخراج نام روز هفته از عنوان (مثلاً «روز اول - سه‌شنبه» -> «سه‌شنبه»)
        title_parts = [p.strip() for p in d["title"].split("-") if p.strip()]
        short_day_name = title_parts[-1] if len(title_parts) > 1 else d["title"]
        daily_stats.append(
            {
                "day_index": d_idx + 1,
                "label": short_day_name,
                "hours": hrs,
                "hours_fa": to_persian_digits(hrs_str),
            }
        )

    # گرد کردن تعداد تست هر درس به مضرب ۱۰ و محاسبه مجموع گردشده
    subject_tests_rounded: dict[str, int] = {}
    for subj, raw_t in subject_tests_raw.items():
        subject_tests_rounded[subj] = round_to_nearest_10(raw_t)

    total_tests_rounded = round_to_nearest_10(total_week_tests_raw)
    if subject_tests_rounded:
        # برای همخوانی جمع جدول با ردیف‌های گردشده:
        total_tests_rounded = round_to_nearest_10(sum(subject_tests_rounded.values()))

    total_hours_float = round(total_week_minutes / 60.0, 2)
    avg_daily_hours = round(total_hours_float / max(1, len(days)), 1)

    return {
        "days": days,
        "summary": {
            "num_days": len(days),
            "total_minutes": total_week_minutes,
            "total_hours": total_hours_float,
            "avg_daily_hours": avg_daily_hours,
            "total_tests_raw": total_week_tests_raw,
            "total_tests": total_tests_rounded,
            "total_parts": total_parts_count,
            "subject_minutes": subject_minutes,
            "subject_tests": subject_tests_rounded,
            "subject_tests_raw": subject_tests_raw,
            "subject_topics": subject_topics,
            "part_type_minutes": part_type_minutes,
            "part_type_counts": part_type_counts,
            "daily_stats": daily_stats,
        },
    }
