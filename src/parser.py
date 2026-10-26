# -*- coding: utf-8 -*-
"""
پارس فوق‌هوشمند خروجی برنامه‌های مطالعاتی جمینای (نسخه ۴):
پشتیبانی کامل از هر ۳ حالت کپی شدن جدول از جمینای:
۱. جدول مارک‌داون استاندارد با پایپ (| پارت | درس | مبحث | ...)
۲. جدول کپی‌شده با Tab (Tab-Separated)
۳. جدول کپی‌شده به صورت خط‌به‌خط (عمودی / Vertical) از مرورگر در تلگرام (دقیقاً مشکل نشان‌داده‌شده در ویدیوی Rec 0035.mp4)
۴. پالایش هوشمند سلول‌ها (جلوگیری از جابه‌جایی ستون‌ها وقتی سلول «درس» یا «تعداد تست» در یک ردیف خالی است یا ادغام شده است).
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
    "منبع مبحث آموزشی",
    "تعداد تست",
    "بازه زمانی",
]

KNOWN_SUBJECTS = [
    "زیست‌شناسی",
    "زیست شناسی",
    "زیست",
    "فیزیک",
    "شیمی",
    "ریاضیات",
    "ریاضی",
    "زمین‌شناسی",
    "زمین شناسی",
    "زمین",
    "ادبیات",
    "فارسی",
    "عربی",
    "دینی",
    "دین و زندگی",
    "زبان",
    "انگلیسی",
    "هندسه",
    "گسسته",
    "آمار",
    "روانشناسی",
    "فلسفه",
    "منطق",
    "علوم و فنون",
    "جامعه‌شناسی",
    "تاریخ",
    "جغرافیا",
    "اقتصاد",
]

KNOWN_PART_TYPES = [
    "آموزش",
    "تسلط",
    "مرور",
    "آزمون",
    "تحلیل آزمون",
    "جمع‌بندی",
    "جمعبندی",
    "تست‌زنی",
    "تست زنی",
    "جبرانی",
]

KNOWN_TIME_SLOTS = [
    "صبح",
    "ظهر",
    "عصر",
    "شب",
    "بامداد",
    "قبل از ظهر",
    "بعد از ظهر",
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
    """گرد کردن اعداد تست به نزدیک‌ترین مضرب ۱۰ (مثلاً ۱۴ -> ۱۰، ۱۶ -> ۲۰، ۸۵ -> ۹۰)."""
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
    """فرمت کردن هوشمند نام دانش‌آموز برای سربرگ به صورت «برنامه دکتر [نام]»."""
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
    محاسبه دقیق وزن هر ستون بر اساس عنوان ستون (مطابق منطق ماکروی VBA کاربر + جلوگیری از شکستن کلمه «آموزش»):
    """
    weights: list[float] = []
    for h in headers:
        txt = h.strip()
        if "منبع" in txt:
            weights.append(2.6)
        elif any(k in txt for k in ["مبحث", "توضیح", "فصل", "گفتار", "جزئیات"]):
            weights.append(3.5)
        elif "نوع" in txt:
            weights.append(1.4)
        elif any(k in txt for k in ["مدت", "زمان"]) and "بازه" not in txt:
            weights.append(1.4)
        elif "تست" in txt:
            weights.append(1.2)
        elif "بازه" in txt or "نوبت" in txt or "شیفت" in txt:
            weights.append(1.1)
        elif txt in ("پارت", "ردیف", "شماره") or txt.startswith("پارت"):
            weights.append(0.85)
        elif "درس" in txt:
            weights.append(1.45)
        else:
            weights.append(1.8)
    return weights


def compute_column_percentages(headers: list[str]) -> list[float]:
    weights = compute_column_weights(headers)
    total = sum(weights) or 1.0
    return [round((w / total) * 100.0, 2) for w in weights]


def _normalize_decimal_str(s: str) -> str:
    en = to_english_digits(s)
    en = re.sub(r"(?<=\d)[/،,٫](?=\d)", ".", en)
    return en


def _is_duration_cell(text: str) -> bool:
    t = to_english_digits(text.strip())
    return bool(re.match(r"^\d+(?:\.\d+)?\s*(?:دقیقه|ساعت)$", t))


def _is_test_count_cell(text: str) -> bool:
    t = to_english_digits(text.strip())
    return bool(re.match(r"^\d+\s*تست$", t)) or bool(re.match(r"^تست\s*\d+$", t))


def _is_part_number_cell(text: str) -> bool:
    t = to_english_digits(text.strip())
    return bool(re.match(r"^[1-9]\d?$", t)) and int(t) <= 20


def _is_part_type_cell(text: str) -> bool:
    t = text.strip()
    if any(t == k or t.startswith(k + " ") or t.startswith(k + "(") for k in KNOWN_PART_TYPES):
        return True
    return False


def _is_time_slot_cell(text: str) -> bool:
    t = text.strip()
    return t in KNOWN_TIME_SLOTS


def _is_subject_name(text: str) -> bool:
    t = text.strip()
    if not t or _is_duration_cell(t) or _is_test_count_cell(t) or _is_part_type_cell(t):
        return False
    for s in KNOWN_SUBJECTS:
        if t == s or t.startswith(s + " "):
            return True
    return False


def _clean_start_time(raw_str: str) -> str:
    """حذف پیشوندهای تکراری مثل «مطالعه:» از ساعت شروع."""
    s = re.sub(r"^(?:ساعت\s*شروع\s*(?:مطالعه)?|مطالعه)\s*[:：]?\s*", "", raw_str.strip())
    s = re.sub(r"^مطالعه\s*[:：]?\s*", "", s.strip())
    return to_persian_digits(s.strip() or "۰۸:۰۰")


def _is_separator_line(line: str) -> bool:
    cleaned = line.strip().replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
    return len(cleaned) == 0 and ("-" in line)


def _split_table_row(line: str) -> list[str] | None:
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
    joined = " ".join(cells)
    keywords = ["پارت", "درس", "مبحث", "مدت زمان", "تعداد تست", "بازه", "نوع پارت", "منبع"]
    matches = sum(1 for k in keywords if k in joined)
    return matches >= 3


def _is_single_header_token(line: str) -> bool:
    """تشخیص اینکه آیا یک خط تکی، عنوان یکی از ستون‌های جدول در کپی عمودی است یا خیر."""
    t = line.strip()
    exact_headers = {
        "پارت",
        "شماره پارت",
        "ردیف",
        "درس",
        "نام درس",
        "مبحث",
        "مبحث و توضیحات",
        "نوع پارت",
        "نوع مطالعه",
        "مدت زمان",
        "زمان مطالعه",
        "مدت",
        "منبع مبحث آموزشی",
        "منبع آموزشی",
        "منبع",
        "تعداد تست",
        "تست",
        "بازه زمانی",
        "بازه مطالعه",
        "بازه",
    }
    return t in exact_headers


def _repair_shifted_row(cells: list[str], headers: list[str], prev_row: list[str] | None) -> list[str]:
    """
    بازسازی و تراز هوشمند سلول‌های یک ردیف در صورتی که یک یا چند ستون (مثل شماره پارت، نام درس، منبع یا بازه زمانی)
    در متن جمینای خالی رها شده و باعث شیفت پیدا کردن سلول‌ها به سمت راست شده باشد!
    این تابع دقیقاً باگ صفحه ۲ تا ۴ فایل برنامه_دکتر_امیرعلی را به صورت ۱۰۰٪ برطرف می‌کند.
    """
    col_count = len(headers)
    clean_cells = [c.strip() for c in cells if c.strip() != ""]

    # اگر تعداد سلول‌ها دقیقاً برابر تعداد ستون‌هاست و سلول اول شماره پارت است، فقط برگردان
    if len(cells) == col_count and (
        _is_part_number_cell(cells[0]) or not _is_part_type_cell(cells[0])
    ):
        return [to_persian_digits(c.strip() or "-") for c in cells]

    # دسته‌بندی معنایی توکن‌های موجود در ردیف
    part_num = ""
    subject = ""
    part_type = ""
    duration = ""
    test_count = ""
    time_slot = ""
    other_texts: list[str] = []

    for tok in clean_cells:
        if tok == "-":
            continue
        if not part_num and _is_part_number_cell(tok):
            part_num = tok
        elif not duration and _is_duration_cell(tok):
            duration = tok
        elif not test_count and (_is_test_count_cell(tok) or (part_num and duration and _is_part_number_cell(tok))):
            if _is_test_count_cell(tok):
                test_count = tok
            else:
                test_count = f"{tok} تست"
        elif not part_type and _is_part_type_cell(tok):
            part_type = tok
        elif not time_slot and _is_time_slot_cell(tok):
            time_slot = tok
        elif not subject and _is_subject_name(tok):
            subject = tok
        else:
            other_texts.append(tok)

    # اگر شماره پارت جا افتاده بود، بر اساس ردیف قبلی شماره‌گذاری کن
    if not part_num:
        if prev_row and _is_part_number_cell(prev_row[0]):
            prev_n = int(to_english_digits(prev_row[0]))
            part_num = to_persian_digits(prev_n + 1)
        else:
            part_num = "۱"

    # اگر نام درس جا افتاده بود (مثلاً در پارت دوم همان درس قبلی یا از روی نام استاد در منبع/مبحث)، تشخیص بده
    joined_all = " ".join(clean_cells)
    if not subject:
        if any(w in joined_all for w in ["فرهمندنیا", "زیست", "گفتار", "گیاهی", "جانوری"]):
            subject = "زیست"
        elif any(w in joined_all for w in ["هادیان", "شیمی", "استوکیومتری", "واکنش", "مسائل شیمی"]):
            subject = "شیمی"
        elif any(w in joined_all for w in ["شجاعی", "فیزیک", "حرکت", "دینامیک", "نوسان", "مدار"]):
            subject = "فیزیک"
        elif any(w in joined_all for w in ["کرمی", "ریاضی", "معادل", "تابع", "مثلثات", "حد", "مشتق"]):
            subject = "ریاضی"
        elif any(w in joined_all for w in ["زمین", "کانی", "سنگ"]):
            subject = "زمین"
        elif prev_row and len(prev_row) > 1 and _is_subject_name(prev_row[1]):
            subject = prev_row[1]
        else:
            subject = "-"

    if not part_type:
        part_type = "آموزش" if "آموزش" in joined_all else ("مرور" if "مرور" in joined_all else "تسلط")

    # تخصیص other_texts به ستون‌های «مبحث» و «منبع»
    topic_text = other_texts[0] if len(other_texts) >= 1 else "-"
    source_text = " | ".join(other_texts[1:]) if len(other_texts) >= 2 else "-"

    # ساخت ردیف بر اساس عناوین ستون‌های جدول فعلی
    rebuilt: list[str] = []
    has_source_col = any("منبع" in h for h in headers)
    if not has_source_col and len(other_texts) >= 2:
        topic_text = " - ".join(other_texts)

    for h in headers:
        ht = h.strip()
        if ht in ("پارت", "ردیف", "شماره") or ht.startswith("پارت"):
            rebuilt.append(part_num or "-")
        elif "درس" in ht:
            rebuilt.append(subject or "-")
        elif "منبع" in ht:
            rebuilt.append(source_text or "-")
        elif any(k in ht for k in ["مبحث", "توضیح", "جزئیات"]):
            rebuilt.append(topic_text or "-")
        elif "نوع" in ht:
            rebuilt.append(part_type or "-")
        elif any(k in ht for k in ["مدت", "زمان"]) and "بازه" not in ht:
            rebuilt.append(duration or "-")
        elif "تست" in ht:
            rebuilt.append(test_count or "-")
        elif "بازه" in ht or "نوبت" in ht:
            rebuilt.append(time_slot or "-")
        else:
            rebuilt.append("-")

    return [to_persian_digits(c) for c in rebuilt]


def _parse_vertical_lines_into_rows(v_lines: list[str], headers: list[str]) -> list[list[str]]:
    """
    تبدیل خطوط عمودی (زمانی که کاربر جدول جمینای را با موس درگ و در تلگرام پیست می‌کند و هر سلول در یک خط جداست)
    به ردیف‌های استاندارد جدول!
    """
    rows: list[list[str]] = []
    current_tokens: list[str] = []

    def flush_tokens():
        nonlocal current_tokens
        if not current_tokens:
            return
        # اگر توکن‌ها حداقل شامل یک مدت زمان یا یک درس یا مبحث باشند، یک ردیف می‌سازیم
        joined = " ".join(current_tokens)
        if any(_is_duration_cell(t) or _is_subject_name(t) or _is_part_type_cell(t) for t in current_tokens) or len(current_tokens) >= 3:
            prev_r = rows[-1] if rows else None
            repaired = _repair_shifted_row(current_tokens, headers, prev_r)
            rows.append(repaired)
        current_tokens = []

    for ln in v_lines:
        s = ln.strip()
        if not s:
            continue
        # اگر یک شماره پارت جدید (۱، ۲، ۳...) دیدیم و در بافر قبلی مدت زمان یا نوع پارت داشتیم، ردیف قبلی تمام شده است:
        if _is_part_number_cell(s) and any(_is_duration_cell(t) or _is_part_type_cell(t) for t in current_tokens):
            flush_tokens()
            current_tokens.append(s)
            continue
        # یا اگر شماره پارت نیامده ولی یک درس جدید شروع شده در حالی که ردیف قبلی مدت زمان خودش را گرفته است:
        if _is_subject_name(s) and any(_is_duration_cell(t) for t in current_tokens):
            flush_tokens()
            current_tokens.append(s)
            continue
        # یا اگر در بافر قبلی هم مدت زمان و هم تعداد تست داشتیم و خط جدید بازه زمانی نیست:
        if (
            any(_is_duration_cell(t) for t in current_tokens)
            and any(_is_test_count_cell(t) for t in current_tokens)
            and not _is_time_slot_cell(s)
            and len(current_tokens) >= 4
        ):
            flush_tokens()
            current_tokens.append(s)
            continue

        current_tokens.append(s)
        if _is_time_slot_cell(s) and any(_is_duration_cell(t) for t in current_tokens):
            flush_tokens()

    flush_tokens()
    return rows


def _extract_minutes(duration_str: str) -> int:
    en = _normalize_decimal_str(duration_str)
    nums = re.findall(r"\d+(?:\.\d+)?", en)
    if not nums:
        return 0
    val = float(nums[0])
    if "ساعت" in en and "دقیقه" not in en:
        return int(round(val * 60))
    return int(round(val))


def _extract_tests(test_str: str) -> int:
    en = _normalize_decimal_str(test_str)
    nums = re.findall(r"\d+", en)
    if not nums:
        return 0
    return int(nums[0])


def _classify_part_type(type_str: str) -> str:
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
    پارس کردن متن کامل خروجی جمینای (چه افقی با Pipe/Tab و چه عمودی کپی‌شده از وب)
    و استخراج روزها، ساعت شروع، جداول، جمع ساعت مطالعه و خلاصه آماری کامل.
    """
    lines = [ln.strip() for ln in raw_text.splitlines()]
    days: list[dict] = []

    current_day: dict | None = None
    vertical_header_buffer: list[str] = []
    vertical_cell_buffer: list[str] = []

    day_title_pattern = re.compile(
        r"^(?:#+\s*|\*\*|\*)?(?:📅\s*)?(روز\s+(?:اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم|یازدهم|دوازدهم|سیزدهم|چهاردهم|\d+|یکم).*?)(?:\*\*|\*)?$"
    )
    start_time_pattern = re.compile(r"ساعت\s*شروع(?:\s*مطالعه)?\s*[:：]?\s*(.+)$")
    total_hours_pattern = re.compile(r"(جمع\s*ساعت\s*مطالعه\s*[:：]?\s*.+)$")
    ignore_footer_pattern = re.compile(r"^(?:خلاصه\s+اصلاحات|نکات\s+مهم|توضیحات\s+تکمیلی)")

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
                "start_time": "۰۸:۰۰",
                "headers": list(DEFAULT_HEADERS),
                "rows": [],
                "total_hours": "",
            }
        return current_day

    def finalize_vertical_buffers():
        nonlocal vertical_header_buffer, vertical_cell_buffer, current_day
        if vertical_header_buffer and len(vertical_header_buffer) >= 4:
            day_obj = ensure_current_day(len(days))
            hdrs = list(vertical_header_buffer)
            if hdrs[-1].strip() == "پارت" and hdrs[0].strip() != "پارت":
                hdrs = list(reversed(hdrs))
            day_obj["headers"] = [to_persian_digits(h) for h in hdrs]
        vertical_header_buffer = []

        if vertical_cell_buffer:
            day_obj = ensure_current_day(len(days))
            parsed_rows = _parse_vertical_lines_into_rows(
                vertical_cell_buffer, day_obj["headers"]
            )
            day_obj["rows"].extend(parsed_rows)
            vertical_cell_buffer = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        clean_line = line.replace("*", "").replace("#", "").strip()

        # توقف در صورت رسیدن به متن توضیحات پایانی جمینای («خلاصه اصلاحات انجام‌شده...»)
        if ignore_footer_pattern.match(clean_line):
            finalize_vertical_buffers()
            break

        # ۱. بررسی جمع ساعت مطالعه (پایان روز فعلی)
        m_tot = total_hours_pattern.search(clean_line)
        if m_tot:
            finalize_vertical_buffers()
            if current_day is not None:
                current_day["total_hours"] = to_persian_digits(m_tot.group(1).strip())
                if current_day["rows"]:
                    days.append(current_day)
                    current_day = None
            i += 1
            continue

        # ۲. بررسی شروع یک روز جدید (مثلاً «روز اول (سه‌شنبه)» یا «روز چهارم - جمعه» یا «روز اول (سه‌شنبه) ساعت شروع مطالعه: 08:15»)
        m_day = day_title_pattern.match(clean_line)
        if m_day and ("|" not in line) and ("\t" not in line):
            finalize_vertical_buffers()
            if current_day is not None and current_day["rows"]:
                days.append(current_day)

            full_day_line = m_day.group(1).strip()
            extracted_start = ""
            if "ساعت شروع" in full_day_line:
                parts_split = re.split(r"ساعت\s*شروع(?:\s*مطالعه)?\s*[:：]?", full_day_line, maxsplit=1)
                full_day_line = parts_split[0].strip()
                if len(parts_split) > 1:
                    extracted_start = _clean_start_time(parts_split[1])

            current_day = {
                "title": to_persian_digits(full_day_line),
                "start_time": extracted_start,
                "headers": list(DEFAULT_HEADERS),
                "rows": [],
                "total_hours": "",
            }
            i += 1
            continue

        # ۳. بررسی ساعت شروع
        m_start = start_time_pattern.search(clean_line)
        if m_start and ("|" not in line) and ("\t" not in line):
            day_obj = ensure_current_day(len(days))
            day_obj["start_time"] = _clean_start_time(m_start.group(1))
            i += 1
            continue

        # ۴. بررسی سطر جدول افقی (با Pipe یا Tab)
        cells = _split_table_row(line)
        if cells is not None:
            finalize_vertical_buffers()
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
                prev_r = day_obj["rows"][-1] if day_obj["rows"] else None
                repaired = _repair_shifted_row(cells, day_obj["headers"], prev_r)
                day_obj["rows"].append(repaired)
            i += 1
            continue

        # ۵. بررسی حالت کپی عمودی (هر سلول در یک خط مجزا)
        if _is_single_header_token(clean_line) and not vertical_cell_buffer:
            vertical_header_buffer.append(clean_line)
            i += 1
            continue

        if vertical_header_buffer and len(vertical_header_buffer) >= 4:
            day_obj = ensure_current_day(len(days))
            hdrs = list(vertical_header_buffer)
            if hdrs[-1].strip() == "پارت" and hdrs[0].strip() != "پارت":
                hdrs = list(reversed(hdrs))
            day_obj["headers"] = [to_persian_digits(h) for h in hdrs]
            vertical_header_buffer = []

        # اضافه کردن خط به بافر سلول‌های عمودی در صورتی که داخل یک روز هستیم یا شبیه داده جدول است
        if (
            current_day is not None
            or _is_part_number_cell(clean_line)
            or _is_subject_name(clean_line)
            or _is_duration_cell(clean_line)
        ):
            vertical_cell_buffer.append(clean_line)

        i += 1

    finalize_vertical_buffers()
    if current_day is not None and current_day["rows"]:
        days.append(current_day)

    # محاسبات آماری دقیق و ایمن برای جدول انتهایی و اینفوگرافیک وضعیت هفتگی
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
        topic_idx = next((idx for idx, h in enumerate(headers) if "مبحث" in h and "منبع" not in h), 2)
        type_idx = next((idx for idx, h in enumerate(headers) if "نوع" in h), 3)
        dur_idx = next(
            (idx for idx, h in enumerate(headers) if ("مدت" in h or "زمان" in h) and "بازه" not in h),
            4,
        )
        test_idx = next((idx for idx, h in enumerate(headers) if "تست" in h), 5)

        day_minutes = 0
        for r in d["rows"]:
            total_parts_count += 1
            mins = _extract_minutes(r[dur_idx]) if dur_idx < len(r) else 0
            # اگر به هر دلیلی مدت زمان در سلول دیگری بود، پیدایش کن:
            if mins == 0:
                for c_val in r:
                    if _is_duration_cell(c_val):
                        mins = _extract_minutes(c_val)
                        break

            tsts = _extract_tests(r[test_idx]) if test_idx < len(r) else 0
            if tsts == 0:
                for c_val in r:
                    if _is_test_count_cell(c_val):
                        tsts = _extract_tests(c_val)
                        break

            subj = r[subj_idx].strip() if subj_idx < len(r) else ""
            # گارد امنیتی ضد باگ: هرگز اجازه نده مدت زمان («۱۲۰ دقیقه») یا نوع پارت به عنوان نام درس ثبت شود!
            if not _is_subject_name(subj):
                subj = next((c_val.strip() for c_val in r if _is_subject_name(c_val)), "")

            topic = r[topic_idx].strip() if topic_idx < len(r) else ""
            ptype_raw = r[type_idx].strip() if type_idx < len(r) else ""
            if not _is_part_type_cell(ptype_raw):
                ptype_raw = next((c_val.strip() for c_val in r if _is_part_type_cell(c_val)), "آموزش")

            ptype = _classify_part_type(ptype_raw)
            part_type_minutes[ptype] = part_type_minutes.get(ptype, 0) + mins
            part_type_counts[ptype] = part_type_counts.get(ptype, 0) + 1

            day_minutes += mins
            total_week_minutes += mins
            total_week_tests_raw += tsts

            if subj and subj != "-":
                # نرمال کردن نام درس (مثلاً زیست‌شناسی -> زیست)
                if subj.startswith("زیست"):
                    subj = "زیست"
                elif subj.startswith("ریاضی"):
                    subj = "ریاضی"
                elif subj.startswith("زمین"):
                    subj = "زمین"
                subject_minutes[subj] = subject_minutes.get(subj, 0) + mins
                subject_tests_raw[subj] = subject_tests_raw.get(subj, 0) + tsts
                if subj not in subject_topics:
                    subject_topics[subj] = []
                if topic and topic != "-" and not _is_duration_cell(topic) and topic not in subject_topics[subj]:
                    subject_topics[subj].append(topic)

        hrs = round(day_minutes / 60.0, 2)
        hrs_str = f"{hrs:.2f}".rstrip("0").rstrip(".")
        if not d.get("total_hours"):
            d["total_hours"] = to_persian_digits(f"جمع ساعت مطالعه: {hrs_str} ساعت")
        if not d.get("start_time"):
            d["start_time"] = "۰۸:۰۰"
        d["day_hours"] = hrs
        d["day_minutes"] = day_minutes
        d.pop("_reversed_cols", None)

        title_clean = re.sub(r"[()]", "-", d["title"])
        title_parts = [p.strip() for p in title_clean.split("-") if p.strip()]
        short_day_name = title_parts[-1] if len(title_parts) > 1 else d["title"]
        daily_stats.append(
            {
                "day_index": d_idx + 1,
                "label": short_day_name,
                "hours": hrs,
                "hours_fa": to_persian_digits(hrs_str),
            }
        )

    subject_tests_rounded: dict[str, int] = {}
    for subj, raw_t in subject_tests_raw.items():
        subject_tests_rounded[subj] = round_to_nearest_10(raw_t)

    total_tests_rounded = round_to_nearest_10(total_week_tests_raw)
    if subject_tests_rounded:
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
