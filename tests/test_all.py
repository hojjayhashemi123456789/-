# -*- coding: utf-8 -*-
import datetime
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
from bot import TelegramStudyPlanBot, build_pdf_filenames


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


def test_parser_and_rounding():
    assert round_to_nearest_10(85) == 90
    assert round_to_nearest_10(75) == 80
    assert round_to_nearest_10(58) == 60
    assert round_to_nearest_10(23) == 20
    assert round_to_nearest_10(14) == 10

    assert format_doctor_student_title("نرگس") == "برنامه دکتر نرگس"
    assert format_doctor_student_title("نرگس خانوم") == "برنامه دکتر نرگس خانوم"

    d = datetime.date(2026, 10, 26)
    r = compute_plan_date_range(d, 7)
    f_main, f_status = build_pdf_filenames("نرگس خانوم", r)
    assert f_main == "برنامه دکتر نرگس خانوم - دوشنبه ۴ آبان.pdf"
    assert f_status == "وضعیت هفتگی - برنامه دکتر نرگس خانوم - دوشنبه ۴ آبان.pdf"


def test_db_operations(tmp_path: Path):
    db = ConsultingDatabase(tmp_path / "test.db")
    items = db.list_students_with_ids()
    assert len(items) >= 18
    db.add_or_touch_student("نرگس خانوم")
    assert "نرگس خانوم" in db.list_students()


def test_v3_conversation_flow(tmp_path: Path):
    """تست کامل ترتیب ۳ مرحله‌ای جدید بات: ۱. تاریخ -> ۲. نام دانش‌آموز -> ۳. پرسش خروجی دوم + دکمه‌های بازگشت."""
    bot = TelegramStudyPlanBot(token="TEST_TOKEN", db_path=str(tmp_path / "flow.db"))
    sent_messages = []
    sent_docs = []

    bot.send_message = lambda chat_id, text, reply_markup=None, parse_mode="HTML": sent_messages.append(
        {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
    ) or {"ok": True}
    bot.edit_message_text = lambda chat_id, message_id, text, reply_markup=None, parse_mode="HTML": sent_messages.append(
        {"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "edited": True}
    ) or {"ok": True}
    bot.answer_callback = lambda callback_id, text="": None
    bot.send_document = lambda chat_id, file_path, filename, caption="", reply_markup=None: sent_docs.append(
        {"filename": filename, "caption": caption, "size": file_path.stat().st_size}
    ) or {"ok": True}

    chat_id = 1176839639
    # ۱. ارسال متن برنامه -> باید وارد STEP1_ASK_DATE شود
    bot.handle_message({"chat": {"id": chat_id}, "text": SAMPLE_GEMINI_PLAN})
    sess = bot._get_session(chat_id)
    assert sess["state"] == "STEP1_ASK_DATE"
    assert "این برنامه ۷ روزه از کی چیده بشه؟" in sent_messages[-1]["text"]

    # ۲. کلیک روی «از فردا» -> باید وارد STEP2_ASK_STUDENT شود
    bot.handle_callback(
        {"id": "cb1", "message": {"chat": {"id": chat_id}, "message_id": 10}, "data": "step1_date:tomorrow"}
    )
    assert sess["state"] == "STEP2_ASK_STUDENT"
    assert "اسم این دانش‌آموز چیه؟" in sent_messages[-1]["text"]

    # ۳. تست دکمه بازگشت به مرحله ۱ (تاریخ)
    bot.handle_callback(
        {"id": "cb2", "message": {"chat": {"id": chat_id}, "message_id": 10}, "data": "back:to_step1"}
    )
    assert sess["state"] == "STEP1_ASK_DATE"

    # ۴. انتخاب مجدد «از امروز» -> ورود به STEP2_ASK_STUDENT
    bot.handle_callback(
        {"id": "cb3", "message": {"chat": {"id": chat_id}, "message_id": 10}, "data": "step1_date:today"}
    )
    assert sess["state"] == "STEP2_ASK_STUDENT"

    # ۵. تایپ نام دانش‌آموز «نرگس خانوم» -> باید وارد STEP3_ASK_SECOND_PDF شود
    bot.handle_message({"chat": {"id": chat_id}, "text": "نرگس خانوم"})
    assert sess["state"] == "STEP3_ASK_SECOND_PDF"
    assert "خروجی دومی" in sent_messages[-1]["text"]
    assert "برنامه دکتر نرگس خانوم" in sent_messages[-1]["text"]

    # ۶. تست دکمه بازگشت از مرحله ۳ به مرحله ۲ (انتخاب دانش‌آموز)
    bot.handle_callback(
        {"id": "cb4", "message": {"chat": {"id": chat_id}, "message_id": 11}, "data": "back:to_step2"}
    )
    assert sess["state"] == "STEP2_ASK_STUDENT"

    # ۷. انتخاب دانش‌آموز از روی دکمه شیشه‌ای -> ورود به STEP3_ASK_SECOND_PDF
    first_stu_id = bot.db.list_students_with_ids()[0]["id"]
    bot.handle_callback(
        {"id": "cb5", "message": {"chat": {"id": chat_id}, "message_id": 11}, "data": f"step2_stu:{first_stu_id}"}
    )
    assert sess["state"] == "STEP3_ASK_SECOND_PDF"

    # ۸. انتخاب «آره، خروجی دوم رو هم بده» -> باید هر ۲ فایل PDF ساخته و ارسال شوند
    bot.handle_callback(
        {"id": "cb6", "message": {"chat": {"id": chat_id}, "message_id": 11}, "data": "step3_out:both"}
    )
    assert len(sent_docs) == 2
    assert sent_docs[0]["filename"].startswith("برنامه دکتر ")
    assert sent_docs[1]["filename"].startswith("وضعیت هفتگی - برنامه دکتر ")
    assert sess["state"] == "IDLE"


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
