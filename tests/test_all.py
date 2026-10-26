# -*- coding: utf-8 -*-
import datetime
import time
from pathlib import Path
from src.jalali import (
    gregorian_to_jalali,
    jalali_to_gregorian,
    format_jalali_date,
    compute_plan_date_range,
)
from src.parser import (
    parse_study_plan,
    compute_column_weights,
    round_to_nearest_10,
    format_doctor_student_title,
)
from src.pdf_generator import generate_study_plan_pdf, generate_weekly_status_pdf
from src.db import ConsultingDatabase


SAMPLE_GEMINI_PLAN = """
روز اول - سه‌شنبه
ساعت شروع: 8:15
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | زیست | فصل یک دوازدهم | تسلط | 90 دقیقه | 16 | صبح |
| ۲ | فیزیک | سرعت ثابت | آموزش (بخش اول) | 120 دقیقه | 8 | صبح |
| ۳ | شیمی | استوکیومتری | تسلط | 90 دقیقه | 15 | عصر |
| ۴ | زیست | گفتار ۱ فصل ۱ دهم | آموزش (بخش اول) | 120 دقیقه | 7 | عصر |
جمع ساعت مطالعه: 7 ساعت

روز دوم - چهارشنبه
ساعت شروع: 8:30
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | فیزیک | سرعت ثابت | آموزش (بخش دوم) | 120 دقیقه | 7 | صبح |
| ۲ | شیمی | مباحث بعد از استوکیومتری | آموزش (بخش اول) | 120 دقیقه | 6 | صبح |
| ۳ | زیست | گفتار یک فصل ۱ دهم | آموزش (بخش دوم) | 120 دقیقه | 8 | عصر |
| ۴ | شیمی | استوکیومتری | مرور | 30 دقیقه | - | عصر |
جمع ساعت مطالعه: 6.5 ساعت

روز سوم - پنج‌شنبه
ساعت شروع: 8:00
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | فیزیک | سرعت ثابت | تسلط | 90 دقیقه | 16 | صبح |
| ۲ | شیمی | مباحث بعد از استوکیومتری | آموزش (بخش دوم) | 120 دقیقه | 7 | صبح |
| ۳ | زیست | گفتار یک فصل ۱ دهم | تسلط | 90 دقیقه | 16 | عصر |
| ۴ | فیزیک | شتاب ثابت | آموزش (بخش اول) | 120 دقیقه | 6 | عصر |
جمع ساعت مطالعه: 7 ساعت

روز چهارم - جمعه
ساعت شروع: 8:45
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | شیمی | مباحث بعد از استوکیومتری | تسلط | 90 دقیقه | 15 | صبح |
| ۲ | فیزیک | شتاب ثابت | آموزش (بخش دوم) | 120 دقیقه | 6 | صبح |
| ۳ | زیست | گفتار ۲ فصل یک دهم | آموزش (بخش اول) | 120 دقیقه | 8 | صبح |
| ۴ | زیست | فصل یک دوازدهم | مرور | 60 دقیقه | - | عصر |
جمع ساعت مطالعه: 6.5 ساعت

روز پنجم - شنبه
ساعت شروع: 8:15
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | فیزیک | شتاب ثابت | تسلط | 90 دقیقه | 16 | صبح |
| ۲ | زیست | گفتار ۲ فصل یک دهم | آموزش (بخش دوم) | 120 دقیقه | 7 | صبح |
| ۳ | ریاضی | معادلات نامعادلات | تسلط | 90 دقیقه | 15 | عصر |
| ۴ | شیمی | پارت دوم بعد از استوکیومتری | آموزش (بخش اول) | 120 دقیقه | 8 | عصر |
جمع ساعت مطالعه: 7 ساعت

روز ششم - یکشنبه
ساعت شروع: 8:30
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | زیست | گفتار ۲ فصل یک دهم | تسلط | 90 دقیقه | 16 | صبح |
| ۲ | ریاضی | تعیین علامت | آموزش (بخش اول) | 120 دقیقه | 8 | صبح |
| ۳ | شیمی | پارت دوم بعد از استوکیومتری | آموزش (بخش دوم) | 120 دقیقه | 7 | عصر |
| ۴ | زیست | گفتار ۳ فصل یک دوازدهم | آموزش (بخش اول) | 120 دقیقه | 7 | عصر |
جمع ساعت مطالعه: 7.5 ساعت

روز هفتم - دوشنبه
ساعت شروع: 8:15
| پارت | درس | مبحث | نوع پارت | مدت زمان | تعداد تست | بازه مطالعه |
|---|---|---|---|---|---|---|
| ۱ | فیزیک | انرژی جنبشی | تسلط | 90 دقیقه | 16 | صبح |
| ۲ | زمین | فصل دوم | تسلط | 90 دقیقه | 14 | صبح |
| ۳ | زیست | گفتار ۱ و ۲ فصل یک دهم | مرور | 60 دقیقه | - | صبح |
| ۴ | شیمی | مباحث بعد از استوکیومتری | مرور | 30 دقیقه | - | ظهر |
| ۵ | ریاضی | تعیین علامت | مرور | 60 دقیقه | - | عصر |
| ۶ | فیزیک | سرعت ثابت و شتاب ثابت | مرور | 60 دقیقه | - | عصر |
| ۷ | زمین | فصل یک | مرور | 45 دقیقه | - | عصر |
جمع ساعت مطالعه: 7.25 ساعت
"""


def test_jalali_conversion():
    jy, jm, jd = gregorian_to_jalali(2026, 10, 26)
    assert (jy, jm, jd) == (1405, 8, 4)
    gy, gm, gd = jalali_to_gregorian(1405, 8, 4)
    assert (gy, gm, gd) == (2026, 10, 26)

    d = datetime.date(2026, 10, 26)
    assert format_jalali_date(d, include_weekday=True, include_year=False) == "دوشنبه ۴ آبان"

    r = compute_plan_date_range(d, 7)
    assert r["num_days"] == 7
    assert r["start_full"] == "دوشنبه ۴ آبان"
    assert r["end_full"] == "یکشنبه ۱۰ آبان"
    assert "۴ تا ۱۰ آبان ۱۴۰۵" in r["short_range"]


def test_parser_and_rounding():
    assert round_to_nearest_10(85) == 90
    assert round_to_nearest_10(75) == 80
    assert round_to_nearest_10(58) == 60
    assert round_to_nearest_10(23) == 20
    assert round_to_nearest_10(14) == 10

    assert format_doctor_student_title("نرگس") == "برنامه دکتر نرگس"
    assert format_doctor_student_title("خانم علیپور") == "برنامه دکتر خانم علیپور"
    assert format_doctor_student_title("دکتر نرگس") == "برنامه دکتر نرگس"

    parsed = parse_study_plan(SAMPLE_GEMINI_PLAN)
    assert parsed["summary"]["num_days"] == 7
    assert parsed["summary"]["total_hours"] == 48.75
    # بررسی اینکه تمام اعداد تست دروس مضرب ۱۰ باشند
    for subj, tst in parsed["summary"]["subject_tests"].items():
        assert tst % 10 == 0, f"Subject {subj} test count {tst} is not a multiple of 10"
    assert parsed["summary"]["total_tests"] % 10 == 0
    weights = compute_column_weights(parsed["days"][0]["headers"])
    assert max(weights) == 3.6
    assert min(weights) == 0.9


def test_db_operations(tmp_path: Path):
    db = ConsultingDatabase(tmp_path / "test.db")
    db.add_or_touch_student("نرگس")
    db.add_or_touch_student("خانم علیپور")
    items = db.list_students_with_ids()
    assert len(items) == 2
    first_id = items[0]["id"]
    assert db.get_student_by_id(first_id) in ("نرگس", "خانم علیپور")


def test_pdf_generation(tmp_path: Path):
    parsed = parse_study_plan(SAMPLE_GEMINI_PLAN)
    date_info = compute_plan_date_range(datetime.date(2026, 10, 26), parsed["summary"]["num_days"])
    out_pdf = tmp_path / "sample_plan.pdf"
    out_status = tmp_path / "sample_status.pdf"

    res1 = generate_study_plan_pdf(
        plan_data=parsed,
        student_name="نرگس",
        date_info=date_info,
        output_path=out_pdf,
    )
    res2 = generate_weekly_status_pdf(
        plan_data=parsed,
        student_name="نرگس",
        date_info=date_info,
        output_path=out_status,
    )
    assert res1.exists() and res1.stat().st_size > 50_000
    assert res2.exists() and res2.stat().st_size > 50_000
