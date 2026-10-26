# -*- coding: utf-8 -*-
"""
ربات تلگرام تبدیل برنامه‌های مطالعاتی جمینای به PDF اختصاصی دکتر هاشمی (@DRpdfmakerbot) - نسخه ۴ نهایی
ویژگی‌های نسخه ۴:
۱. پشتیبانی کامل از کپی مستقیم (عمودی / خط‌به‌خط) جدول از مرورگر جمینای در تلگرام (رفع کامل خطای ویدیوی Rec 0035.mp4) + پشتیبانی از جداول مارک‌داون و Tab.
۲. ارسال فایل‌های PDF نهایی کاملاً بدون کپشن (caption="") و بدون دکمه زیر فایل تا مشاور بتواند فایل را مستقیماً برای دانش‌آموز فوروارد کند.
۳. پشتیبانی از فونت Pinar-Regular.ttf و Pinar-Bold.ttf (به همراه امکان آپلود مستقیم فایل فونت جدید .ttf در چت بات برای جایگزینی آنی فونت بولد یا معمولی).
۴. ترتیب ۳ مرحله‌ای دقیق: (۱) انتخاب تاریخ شروع با دکمه‌های شیشه‌ای -> (۲) انتخاب نام دانش‌آموز با دکمه‌های شیشه‌ای ۲ ستونی -> (۳) انتخاب دریافت یا عدم دریافت خروجی دوم (وضعیت هفتگی / اینفوگرافیک).
"""

from __future__ import annotations
import datetime
import json
import logging
import os
import tempfile
import time
from pathlib import Path
import requests

from src.db import ConsultingDatabase
from src.jalali import (
    compute_plan_date_range,
    format_jalali_date,
    get_next_saturday,
    get_tehran_today,
    to_persian_digits,
)
from src.parser import format_doctor_student_title, parse_study_plan
from src.pdf_generator import (
    _get_cached_data_uri,
    clear_asset_cache,
    generate_study_plan_pdf,
    generate_weekly_status_pdf,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("DRpdfmakerbot")

DEFAULT_BOT_TOKEN = "8873737714:AAEjTPhIIBxBQFkHuSuILdEQ6DR0CzLmmBg"
BOT_TOKEN = os.environ.get("BOT_TOKEN", DEFAULT_BOT_TOKEN).strip() or DEFAULT_BOT_TOKEN
DB_PATH = os.environ.get("DB_PATH", "consulting_bot.db")
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

BTN_NEW_PLAN = "🎯📅 برنامه درسی دوره‌ای (ارسال برنامه جدید)"
BTN_STUDENTS = "👥 مدیریت و مشاهده لیست دانش‌آموزان"
BTN_ADD_STUDENT = "🟢👤 افزودن دانش‌آموز جدید (با نام)"
BTN_RECENT_PLANS = "📊 آخرین برنامه‌های صادرشده"
BTN_SETTINGS = "⚙️ تنظیمات پیش‌فرض خروجی"
BTN_RESET = "🔄 شروع مجدد / پاکسازی حافظه"


def build_pdf_filenames(student_name: str, date_info: dict) -> tuple[str, str]:
    """
    ساخت دقیق نام فایل PDF مطابق دستور کاربر:
    «برنامه دکتر [نام دانش‌آموز] - [تاریخ روز اول].pdf»
    """
    doctor_title = format_doctor_student_title(student_name.strip())
    first_day = to_persian_digits(date_info.get("start_full", date_info.get("short_range", ""))).strip()
    safe_title = doctor_title.replace("/", "-").replace("\\", "-")
    safe_day = first_day.replace("/", "-").replace("\\", "-")

    main_filename = f"{safe_title} - {safe_day}.pdf"
    status_filename = f"وضعیت هفتگی - {safe_title} - {safe_day}.pdf"
    return main_filename, status_filename


class TelegramStudyPlanBot:
    def __init__(self, token: str, db_path: str = "consulting_bot.db") -> None:
        self.token = token
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.http = requests.Session()
        self.db = ConsultingDatabase(db_path)
        self.sessions: dict[int, dict] = {}
        self._warm_up_assets()

    def _warm_up_assets(self) -> None:
        try:
            _get_cached_data_uri(ASSETS_DIR / "Pinar-Regular.ttf", "font/ttf")
            if (ASSETS_DIR / "Pinar-Bold.ttf").exists():
                _get_cached_data_uri(ASSETS_DIR / "Pinar-Bold.ttf", "font/ttf")
            _get_cached_data_uri(ASSETS_DIR / "cover_bg.jpg", "image/jpeg")
            _get_cached_data_uri(ASSETS_DIR / "calendar_icon.png", "image/png")
            logger.info("Assets pre-cached in memory for instant PDF rendering.")
        except Exception as exc:
            logger.warning("Could not warm up assets: %s", exc)

    def _api(self, method: str, data: dict | None = None, files: dict | None = None) -> dict:
        url = f"{self.api_base}/{method}"
        try:
            resp = self.http.post(url, data=data, files=files, timeout=60)
            return resp.json()
        except Exception as exc:
            logger.error("Telegram API error (%s): %s", method, exc)
            return {"ok": False, "description": str(exc)}

    @staticmethod
    def build_main_reply_keyboard() -> dict:
        return {
            "keyboard": [
                [{"text": BTN_NEW_PLAN}, {"text": BTN_STUDENTS}],
                [{"text": BTN_ADD_STUDENT}, {"text": BTN_RECENT_PLANS}],
                [{"text": BTN_SETTINGS}, {"text": BTN_RESET}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        }

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        return self._api("sendMessage", data=payload)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        return self._api("editMessageText", data=payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._api(
            "answerCallbackQuery",
            data={"callback_query_id": callback_id, "text": text},
        )

    def send_document(
        self,
        chat_id: int,
        file_path: Path,
        filename: str,
        caption: str = "",
        reply_markup: dict | None = None,
    ) -> dict:
        """
        ارسال فایل PDF در تلگرام.
        مطابق درخواست کاربر، وقتی caption خالی باشد هیچ متنی زیر فایل درج نمی‌شود تا آماده فوروارد مستقیم به دانش‌آموز باشد.
        """
        data_payload: dict = {"chat_id": chat_id}
        if caption:
            data_payload["caption"] = caption
            data_payload["parse_mode"] = "HTML"
        if reply_markup is not None:
            data_payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        with open(file_path, "rb") as f:
            return self._api(
                "sendDocument",
                data=data_payload,
                files={"document": (filename, f, "application/pdf")},
            )

    def _get_session(self, chat_id: int) -> dict:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = {
                "state": "IDLE",
                "raw_chunks": [],
                "plan_data": None,
                "date_info": None,
                "student_name": "",
                "include_summary": True,
                "sync_weekdays": True,
            }
        return self.sessions[chat_id]

    def _build_step1_date_inline_keyboard(self, session: dict) -> dict:
        plan_data = session.get("plan_data") or {}
        num_days = max(1, plan_data.get("summary", {}).get("num_days", 7))
        today = get_tehran_today()
        tomorrow = today + datetime.timedelta(days=1)
        next_sat = get_next_saturday(today)

        r_today = compute_plan_date_range(today, num_days)
        r_tmrw = compute_plan_date_range(tomorrow, num_days)
        r_sat = compute_plan_date_range(next_sat, num_days)

        keyboard = [
            [
                {
                    "text": f"🟢📅 از امروز ({r_today['start_full']} تا {r_today['end_full']})",
                    "callback_data": "step1_date:today",
                }
            ],
            [
                {
                    "text": f"🟡📆 از فردا ({r_tmrw['start_full']} تا {r_tmrw['end_full']})",
                    "callback_data": "step1_date:tomorrow",
                }
            ],
            [
                {
                    "text": f"🟣🗓 از شنبه آینده ({r_sat['start_full']} تا {r_sat['end_full']})",
                    "callback_data": "step1_date:saturday",
                }
            ],
            [
                {
                    "text": "✏️ وارد کردن تاریخ دلخواه",
                    "callback_data": "step1_date:custom",
                },
                {
                    "text": "➕ افزودن بخش دیگر برنامه",
                    "callback_data": "act:append_more",
                },
            ],
            [
                {"text": "❌ لغو و شروع مجدد", "callback_data": "act:reset"},
            ],
        ]
        return {"inline_keyboard": keyboard}

    def _build_step2_student_inline_keyboard(self) -> dict:
        students = self.db.list_students_with_ids(limit=18)
        keyboard: list[list[dict]] = []
        row: list[dict] = []
        for item in students:
            row.append(
                {
                    "text": f"👤 {item['name']}",
                    "callback_data": f"step2_stu:{item['id']}",
                }
            )
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append(
            [
                {"text": "🔙 بازگشت به انتخاب تاریخ", "callback_data": "back:to_step1"},
                {"text": "❌ لغو", "callback_data": "act:reset"},
            ]
        )
        return {"inline_keyboard": keyboard}

    def _build_step3_second_output_inline_keyboard(self, session: dict) -> dict:
        sum_icon = "✅" if session.get("include_summary", True) else "⬜"
        sync_icon = "✅" if session.get("sync_weekdays", True) else "⬜"

        keyboard = [
            [
                {
                    "text": "✅ آره، خروجی دوم (وضعیت هفتگی) رو هم بده!",
                    "callback_data": "step3_out:both",
                }
            ],
            [
                {
                    "text": "📄 نه، فقط همین برنامه مطالعاتی کافیه",
                    "callback_data": "step3_out:main_only",
                }
            ],
            [
                {
                    "text": f"{sum_icon} جدول خلاصه آخر برنامه",
                    "callback_data": "toggle:summary",
                },
                {
                    "text": f"{sync_icon} تطبیق خودکار روز هفته",
                    "callback_data": "toggle:sync",
                },
            ],
            [
                {"text": "🔙 بازگشت به انتخاب دانش‌آموز", "callback_data": "back:to_step2"},
                {"text": "❌ لغو", "callback_data": "act:reset"},
            ],
        ]
        return {"inline_keyboard": keyboard}

    def _show_step1_ask_date(
        self, chat_id: int, session: dict, edit_msg_id: int | None = None
    ) -> None:
        combined_text = "\n\n".join(session["raw_chunks"])
        plan_data = parse_study_plan(combined_text)
        session["plan_data"] = plan_data

        num_days = plan_data["summary"]["num_days"]
        total_hours = plan_data["summary"]["total_hours"]
        total_tests = plan_data["summary"]["total_tests"]

        if num_days == 0:
            self.send_message(
                chat_id,
                "⚠️ <b>جدولی در متن ارسالی شناسایی نشد!</b>\n"
                "لطفاً خروجی جدول برنامه‌ریزی جمینای را کپی و ارسال کنید.",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        session["state"] = "STEP1_ASK_DATE"
        today = get_tehran_today()
        today_str = format_jalali_date(today, include_weekday=True, include_year=True)

        msg = (
            f"✅ <b>فایل برنامه دریافت شد!</b>\n\n"
            f"📊 <b>طول برنامه تشخیص‌داده‌شده:</b> برنامه <b>{to_persian_digits(num_days)} روزه</b>\n"
            f"⏱ <b>مجموع ساعات مطالعه:</b> {to_persian_digits(total_hours)} ساعت\n"
            f"📝 <b>مجموع تست‌ها:</b> حدود {to_persian_digits(total_tests)} تست\n"
            f"📅 <b>تاریخ امروز:</b> {today_str}\n\n"
            f"👇 <b>مرحله ۱ از ۳ — این برنامه {to_persian_digits(num_days)} روزه از کی چیده بشه؟</b>\n"
            f"<i>(از روی دکمه‌های شیشه‌ای زیر انتخاب کنید):</i>"
        )
        markup = self._build_step1_date_inline_keyboard(session)
        if edit_msg_id:
            self.edit_message_text(chat_id, edit_msg_id, msg, reply_markup=markup)
        else:
            self.send_message(chat_id, msg, reply_markup=markup)

    def _show_step2_ask_student(
        self, chat_id: int, session: dict, edit_msg_id: int | None = None
    ) -> None:
        session["state"] = "STEP2_ASK_STUDENT"
        date_info = session["date_info"]
        num_days = session["plan_data"]["summary"]["num_days"]

        msg = (
            f"📅 <b>بازه انتخاب‌شده:</b> {date_info['start_full']} تا {date_info['end_full']} "
            f"(برنامه {to_persian_digits(num_days)} روزه)\n"
            f"📌 <b>تاریخ روز اول برنامه:</b> {date_info['start_full']}\n\n"
            f"👤 <b>مرحله ۲ از ۳ — اسم این دانش‌آموز چیه؟</b>\n"
            f"• از دکمه‌های شیشه‌ای زیر انتخاب کنید یا <b>نام دانش‌آموز را مستقیم تایپ کنید</b> (مثلاً <i>نرگس</i>، <i>نرگس خانوم</i>، <i>امیرعلی</i>).\n"
            f"• ربات به صورت خودکار سرتیتر و نام فایل PDF را <b>«برنامه دکتر [نام دانش‌آموز] - {date_info['start_full']}.pdf»</b> می‌گذارد:"
        )
        markup = self._build_step2_student_inline_keyboard()
        if edit_msg_id:
            self.edit_message_text(chat_id, edit_msg_id, msg, reply_markup=markup)
        else:
            self.send_message(chat_id, msg, reply_markup=markup)

    def _show_step3_ask_second_output(
        self, chat_id: int, session: dict, edit_msg_id: int | None = None
    ) -> None:
        session["state"] = "STEP3_ASK_SECOND_PDF"
        student = session["student_name"].strip()
        date_info = session["date_info"]
        doctor_title = format_doctor_student_title(student)
        main_filename, _ = build_pdf_filenames(student, date_info)

        msg = (
            f"✅ <b>مشخصات برنامه نهایی شد:</b>\n\n"
            f"👤 <b>نام دانش‌آموز:</b> {student}\n"
            f"🏷 <b>سرتیتر داخل برنامه:</b> {doctor_title}\n"
            f"📅 <b>تاریخ روز اول برنامه:</b> {date_info['start_full']}\n"
            f"📂 <b>نام فایل خروجی اول:</b> <code>{main_filename}</code>\n\n"
            f"❓ <b>مرحله ۳ از ۳ — آیا می‌خوای اون خروجی دومی (PDF وضعیت هفتگی / اینفوگرافیک) رو هم بهت بدم یا فقط همین یه خروجی برات کافیه؟</b>"
        )
        markup = self._build_step3_second_output_inline_keyboard(session)
        if edit_msg_id:
            self.edit_message_text(chat_id, edit_msg_id, msg, reply_markup=markup)
        else:
            self.send_message(chat_id, msg, reply_markup=markup)

    def _finalize_and_send_pdfs(
        self, chat_id: int, session: dict, want_status_pdf: bool
    ) -> None:
        """
        تولید و ارسال فایل‌های PDF کاملاً بدون کپشن (caption="") و بدون دکمه روی خود فایل
        تا مشاور بتواند مستقیماً فایل را برای دانش‌آموز فوروارد کند.
        """
        student = session["student_name"].strip()
        plan_data = session["plan_data"]
        date_info = session["date_info"]
        num_days = plan_data["summary"]["num_days"]
        total_hours = plan_data["summary"]["total_hours"]

        main_pdf_filename, status_pdf_filename = build_pdf_filenames(student, date_info)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_main = tmp_path / main_pdf_filename
            generate_study_plan_pdf(
                plan_data=plan_data,
                student_name=student,
                date_info=date_info,
                output_path=out_main,
                assets_dir=ASSETS_DIR,
                include_summary=session.get("include_summary", True),
                sync_weekday_names=session.get("sync_weekdays", True),
            )
            # ارسال کاملاً بدون کپشن و بدون دکمه زیر فایل برای فوروارد مستقیم به دانش‌آموز
            self.send_document(
                chat_id,
                out_main,
                main_pdf_filename,
                caption="",
                reply_markup=None,
            )

            if want_status_pdf:
                out_status = tmp_path / status_pdf_filename
                generate_weekly_status_pdf(
                    plan_data=plan_data,
                    student_name=student,
                    date_info=date_info,
                    output_path=out_status,
                    assets_dir=ASSETS_DIR,
                )
                self.send_document(
                    chat_id,
                    out_status,
                    status_pdf_filename,
                    caption="",
                    reply_markup=None,
                )

        self.db.add_or_touch_student(student)
        self.db.log_plan(student, date_info["short_range"], num_days, total_hours)
        session["state"] = "IDLE"
        session["raw_chunks"] = []
        session["plan_data"] = None
        session["date_info"] = None

    def _send_students_management_panel(self, chat_id: int, edit_msg_id: int | None = None) -> None:
        students = self.db.list_students_with_ids(limit=20)
        keyboard: list[list[dict]] = []
        row: list[dict] = []
        for item in students:
            row.append(
                {
                    "text": f"👤 {item['name']} (🗑)",
                    "callback_data": f"delstu:{item['id']}",
                }
            )
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(
            [{"text": "🟢➕ افزودن دانش‌آموز جدید", "callback_data": "act:add_student_only"}]
        )
        msg = (
            "👥 <b>مدیریت لیست دانش‌آموزان ذخیره‌شده:</b>\n\n"
            "• هنگام ساخت برنامه، این اسامی به صورت دکمه‌های شیشه‌ای ۲ ستونی نمایش داده می‌شوند.\n"
            "• برای <b>حذف</b> هر نام، روی آن کلیک کنید یا برای افزودن نام جدید دکمه زیر را بزنید:"
        )
        markup = {"inline_keyboard": keyboard}
        if edit_msg_id:
            self.edit_message_text(chat_id, edit_msg_id, msg, reply_markup=markup)
        else:
            self.send_message(chat_id, msg, reply_markup=markup)

    def handle_message(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        # پشتیبانی از آپلود مستقیم فونت (.ttf) یا فایل متنی برنامه (.txt / .md)
        if "document" in message:
            doc = message["document"]
            fname = doc.get("file_name", "")
            if fname.lower().endswith(".ttf"):
                f_info = self._api("getFile", data={"file_id": doc["file_id"]})
                if f_info.get("ok"):
                    f_path = f_info["result"]["file_path"]
                    dl_url = f"https://api.telegram.org/file/bot{self.token}/{f_path}"
                    font_bytes = self.http.get(dl_url, timeout=30).content
                    if "bold" in fname.lower() or "black" in fname.lower() or "heavy" in fname.lower():
                        target_font = ASSETS_DIR / "Pinar-Bold.ttf"
                        label = "بولد (Pinar-Bold.ttf)"
                    else:
                        target_font = ASSETS_DIR / "Pinar-Bold.ttf"
                        label = "بولد/سفارشی (Pinar-Bold.ttf)"
                    target_font.write_bytes(font_bytes)
                    clear_asset_cache()
                    self._warm_up_assets()
                    self.send_message(
                        chat_id,
                        f"✅ فونت <b>{fname}</b> با موفقیت به عنوان فونت <b>{label}</b> ذخیره و فعال شد!",
                        reply_markup=self.build_main_reply_keyboard(),
                    )
                    return

            if not text and (fname.endswith(".txt") or fname.endswith(".md")):
                f_info = self._api("getFile", data={"file_id": doc["file_id"]})
                if f_info.get("ok"):
                    f_path = f_info["result"]["file_path"]
                    dl_url = f"https://api.telegram.org/file/bot{self.token}/{f_path}"
                    text = self.http.get(dl_url, timeout=30).content.decode(
                        "utf-8", errors="ignore"
                    )

        if not text:
            return

        session = self._get_session(chat_id)

        if text.startswith("/start") or text.startswith("/help"):
            session["state"] = "IDLE"
            session["raw_chunks"] = []
            today_str = format_jalali_date(get_tehran_today(), include_weekday=True, include_year=True)
            welcome = (
                f"سلام دکتر هاشمی عزیز! 👋🩺\n"
                f"به ربات <b>تبدیل فوق‌سریع برنامه مطالعاتی به PDF و اینفوگرافیک وضعیت هفتگی (با فونت پینار و پینار بولد)</b> خوش آمدید.\n\n"
                f"📅 <b>تاریخ امروز:</b> {today_str}\n\n"
                f"🚀 <b>مراحل کار:</b>\n"
                f"۱️⃣ ابتدا <b>متن برنامه مطالعاتی جمینای</b> را کپی کرده و بفرستید (هم کپی مستقیم از صفحه وب جمینای و هم کپی مارک‌داون پشتیبانی می‌شود).\n"
                f"۲️⃣ با <b>دکمه شیشه‌ای</b> مشخص کنید <b>برنامه از کی چیده بشه؟</b> (امروز / فردا / شنبه آینده).\n"
                f"۳️⃣ <b>نام دانش‌آموز</b> را از دکمه‌های شیشه‌ای انتخاب یا تایپ کنید.\n"
                f"۴️⃣ انتخاب کنید <b>آیا خروجی دوم (وضعیت هفتگی) را هم می‌خواهید یا خیر</b> تا فایل PDF بدون هیچ کپشن اضافه‌ای (آماده فوروارد مستقیم برای دانش‌آموز) ارسال شود!"
            )
            self.send_message(
                chat_id,
                welcome,
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if text == BTN_RESET or text == "/cancel":
            session["state"] = "IDLE"
            session["raw_chunks"] = []
            session["plan_data"] = None
            session["date_info"] = None
            self.send_message(
                chat_id,
                "🔄 حافظه موقت پاک شد. هر زمان آماده بودید متن برنامه جدید را ارسال کنید.",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if text == BTN_NEW_PLAN:
            session["state"] = "IDLE"
            session["raw_chunks"] = []
            self.send_message(
                chat_id,
                "📋 <b>لطفاً متن جدول برنامه مطالعاتی که از جمینای گرفته‌اید را همین‌جا ارسال کنید:</b>",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if text == BTN_STUDENTS or text.startswith("/students"):
            self._send_students_management_panel(chat_id)
            return

        if text == BTN_ADD_STUDENT:
            session["state"] = "ADD_STUDENT_ONLY"
            self.send_message(
                chat_id,
                "👤 <b>نام دانش‌آموز جدید را تایپ و ارسال کنید</b> تا به دکمه‌های شیشه‌ای اضافه شود:",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if text == BTN_RECENT_PLANS:
            recent = self.db.get_recent_plans(limit=8)
            if not recent:
                self.send_message(
                    chat_id,
                    "📭 هنوز برنامه‌ای صادر نشده است.",
                    reply_markup=self.build_main_reply_keyboard(),
                )
            else:
                lines = [
                    f"• <b>{format_doctor_student_title(r['student_name'])}</b> | {r['date_range']} ({to_persian_digits(r['num_days'])} روزه - {to_persian_digits(r['total_hours'])} ساعت)"
                    for r in recent
                ]
                self.send_message(
                    chat_id,
                    "📊 <b>آخرین برنامه‌های صادرشده:</b>\n\n" + "\n".join(lines),
                    reply_markup=self.build_main_reply_keyboard(),
                )
            return

        if text == BTN_SETTINGS:
            sum_icon = "✅ فعال" if session.get("include_summary", True) else "❌ غیرفعال"
            sync_icon = "✅ فعال" if session.get("sync_weekdays", True) else "❌ غیرفعال"
            kb = {
                "inline_keyboard": [
                    [
                        {
                            "text": f"جدول خلاصه آخر برنامه: {sum_icon}",
                            "callback_data": "settings_toggle:summary",
                        }
                    ],
                    [
                        {
                            "text": f"تطبیق روز هفته با تقویم: {sync_icon}",
                            "callback_data": "settings_toggle:sync",
                        }
                    ],
                ]
            }
            self.send_message(
                chat_id,
                "⚙️ <b>تنظیمات پیش‌فرض ساخت PDF:</b>\nبرای تغییر هر مورد روی دکمه شیشه‌ای آن بزنید (همچنین هر زمان فایل فونت <code>.ttf</code> بفرستید خودکار جایگزین فونت بولد می‌شود):",
                reply_markup=kb,
            )
            return

        if session["state"] == "ADD_STUDENT_ONLY":
            self.db.add_or_touch_student(text.strip())
            session["state"] = "IDLE"
            self.send_message(
                chat_id,
                f"✅ دانش‌آموز <b>«{text.strip()}»</b> با موفقیت به لیست دکمه‌های شیشه‌ای اضافه شد!",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        looks_like_plan = (
            ("پارت" in text and "درس" in text)
            or ("ساعت شروع" in text)
            or ("جمع ساعت مطالعه" in text)
            or ("روز اول" in text)
            or ("دقیقه" in text and "تست" in text)
        )

        if session["state"] in ("IDLE", "WAIT_MORE_TEXT") or (
            session["state"] == "STEP1_ASK_DATE" and looks_like_plan and len(text) > 60
        ):
            session["raw_chunks"].append(text)
            self._show_step1_ask_date(chat_id, session)
            return

        if session["state"] == "STEP1_ASK_CUSTOM_DATE":
            num_days = session["plan_data"]["summary"]["num_days"]
            custom_text = to_persian_digits(text.strip())
            session["date_info"] = {
                "num_days": num_days,
                "short_range": custom_text,
                "start_full": custom_text,
                "end_full": f"برنامه {to_persian_digits(num_days)} روزه",
            }
            self._show_step2_ask_student(chat_id, session)
            return

        if session["state"] == "STEP2_ASK_STUDENT":
            if looks_like_plan and len(text) > 60:
                session["raw_chunks"] = [text]
                self._show_step1_ask_date(chat_id, session)
                return
            session["student_name"] = text.strip()
            self.db.add_or_touch_student(text.strip())
            self._show_step3_ask_second_output(chat_id, session)
            return

        if looks_like_plan:
            session["raw_chunks"] = [text]
            self._show_step1_ask_date(chat_id, session)
        else:
            self.send_message(
                chat_id,
                "📋 لطفاً ابتدا متن جدول برنامه مطالعاتی جمینای را ارسال کنید (یا از دکمه‌های منوی پایین صفحه استفاده نمایید).",
                reply_markup=self.build_main_reply_keyboard(),
            )

    def handle_callback(self, callback: dict) -> None:
        cb_id = callback["id"]
        msg_obj = callback.get("message", {})
        chat_id = msg_obj.get("chat", {}).get("id")
        msg_id = msg_obj.get("message_id")
        data = callback.get("data", "")
        if not chat_id:
            return
        session = self._get_session(chat_id)

        self.answer_callback(cb_id)

        if data == "act:reset":
            session["state"] = "IDLE"
            session["raw_chunks"] = []
            session["plan_data"] = None
            session["date_info"] = None
            if msg_id:
                self.edit_message_text(
                    chat_id,
                    msg_id,
                    "🔄 عملیات لغو شد. هر زمان آماده بودید متن برنامه جدید را بفرستید.",
                )
            return

        if data == "act:new_plan_prompt":
            session["state"] = "IDLE"
            session["raw_chunks"] = []
            self.send_message(
                chat_id,
                "📋 <b>لطفاً متن جدول برنامه مطالعاتی جدید را ارسال کنید:</b>",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if data == "act:append_more":
            session["state"] = "WAIT_MORE_TEXT"
            self.send_message(
                chat_id,
                "➕ <b>لطفاً بخش بعدی متن جدول را ارسال کنید</b> تا به روزهای قبلی اضافه شود:",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if data == "act:add_student_only":
            session["state"] = "ADD_STUDENT_ONLY"
            self.send_message(
                chat_id,
                "👤 <b>نام دانش‌آموز جدید را تایپ و ارسال کنید:</b>",
                reply_markup=self.build_main_reply_keyboard(),
            )
            return

        if data.startswith("delstu:"):
            stu_id = int(data.split(":", 1)[1])
            deleted = self.db.delete_student_by_id(stu_id)
            if deleted:
                self._send_students_management_panel(chat_id, edit_msg_id=msg_id)
            return

        if data.startswith("settings_toggle:"):
            key = data.split(":", 1)[1]
            if key == "summary":
                session["include_summary"] = not session.get("include_summary", True)
            elif key == "sync":
                session["sync_weekdays"] = not session.get("sync_weekdays", True)
            sum_icon = "✅ فعال" if session.get("include_summary", True) else "❌ غیرفعال"
            sync_icon = "✅ فعال" if session.get("sync_weekdays", True) else "❌ غیرفعال"
            kb = {
                "inline_keyboard": [
                    [
                        {
                            "text": f"جدول خلاصه آخر برنامه: {sum_icon}",
                            "callback_data": "settings_toggle:summary",
                        }
                    ],
                    [
                        {
                            "text": f"تطبیق روز هفته با تقویم: {sync_icon}",
                            "callback_data": "settings_toggle:sync",
                        }
                    ],
                ]
            }
            if msg_id:
                self.edit_message_text(
                    chat_id,
                    msg_id,
                    "⚙️ <b>تنظیمات پیش‌فرض ساخت PDF:</b>\nبرای تغییر هر مورد روی دکمه شیشه‌ای آن بزنید:",
                    reply_markup=kb,
                )
            return

        if data == "back:to_step1":
            if not session.get("plan_data"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            self._show_step1_ask_date(chat_id, session, edit_msg_id=msg_id)
            return

        if data == "back:to_step2":
            if not session.get("plan_data") or not session.get("date_info"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            self._show_step2_ask_student(chat_id, session, edit_msg_id=msg_id)
            return

        if data.startswith("step1_date:"):
            if not session.get("plan_data"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            choice = data.split(":", 1)[1]
            num_days = max(1, session["plan_data"]["summary"]["num_days"])
            today = get_tehran_today()

            if choice == "today":
                session["date_info"] = compute_plan_date_range(today, num_days)
                self._show_step2_ask_student(chat_id, session, edit_msg_id=msg_id)
            elif choice == "tomorrow":
                tmrw = today + datetime.timedelta(days=1)
                session["date_info"] = compute_plan_date_range(tmrw, num_days)
                self._show_step2_ask_student(chat_id, session, edit_msg_id=msg_id)
            elif choice == "saturday":
                sat = get_next_saturday(today)
                session["date_info"] = compute_plan_date_range(sat, num_days)
                self._show_step2_ask_student(chat_id, session, edit_msg_id=msg_id)
            elif choice == "custom":
                session["state"] = "STEP1_ASK_CUSTOM_DATE"
                back_kb = {
                    "inline_keyboard": [
                        [{"text": "🔙 بازگشت به انتخاب تاریخ", "callback_data": "back:to_step1"}]
                    ]
                }
                if msg_id:
                    self.edit_message_text(
                        chat_id,
                        msg_id,
                        "✏️ <b>لطفاً بازه تاریخ یا تاریخ شروع مورد نظر خود را تایپ کنید:</b>\n"
                        "<i>مثال: دوشنبه ۴ آبان تا یکشنبه ۱۰ آبان</i>",
                        reply_markup=back_kb,
                    )
                else:
                    self.send_message(
                        chat_id,
                        "✏️ <b>لطفاً بازه تاریخ یا تاریخ شروع مورد نظر خود را تایپ کنید:</b>\n"
                        "<i>مثال: دوشنبه ۴ آبان تا یکشنبه ۱۰ آبان</i>",
                        reply_markup=back_kb,
                    )
            return

        if data.startswith("step2_stu:"):
            if not session.get("plan_data") or not session.get("date_info"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            stu_id = int(data.split(":", 1)[1])
            student_name = self.db.get_student_by_id(stu_id) or "دانش‌آموز"
            session["student_name"] = student_name
            self._show_step3_ask_second_output(chat_id, session, edit_msg_id=msg_id)
            return

        if data in ("toggle:summary", "toggle:sync"):
            if data == "toggle:summary":
                session["include_summary"] = not session.get("include_summary", True)
            elif data == "toggle:sync":
                session["sync_weekdays"] = not session.get("sync_weekdays", True)
            self._show_step3_ask_second_output(chat_id, session, edit_msg_id=msg_id)
            return

        if data.startswith("step3_out:"):
            if not session.get("plan_data") or not session.get("date_info"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            mode = data.split(":", 1)[1]
            want_both = mode == "both"
            self._finalize_and_send_pdfs(chat_id, session, want_status_pdf=want_both)
            return

    def run_polling(self) -> None:
        logger.info("Starting @DRpdfmakerbot v4 polling loop...")
        offset = 0
        while True:
            try:
                resp = self.http.get(
                    f"{self.api_base}/getUpdates",
                    params={"offset": offset, "timeout": 25},
                    timeout=35,
                ).json()
                if not resp.get("ok"):
                    time.sleep(3)
                    continue
                for upd in resp.get("result", []):
                    offset = upd["update_id"] + 1
                    if "message" in upd:
                        self.handle_message(upd["message"])
                    elif "callback_query" in upd:
                        self.handle_callback(upd["callback_query"])
            except KeyboardInterrupt:
                logger.info("Bot stopped by user.")
                break
            except Exception as exc:
                logger.error("Polling error: %s", exc)
                time.sleep(3)


if __name__ == "__main__":
    bot = TelegramStudyPlanBot(token=BOT_TOKEN, db_path=DB_PATH)
    bot.run_polling()
