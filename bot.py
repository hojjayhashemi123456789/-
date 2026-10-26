# -*- coding: utf-8 -*-
"""
ربات تلگرام تبدیل برنامه‌های مطالعاتی جمینای به PDF اختصاصی دکتر هاشمی (@DRpdfmakerbot) - نسخه ۲
پشتیبانی از:
- دریافت متن جدول از جمینای (تک‌پیامی، چندپیامی متوالی، یا فایل متنی .txt)
- تشخیص خودکار تعداد روزها، ساعت مطالعه و تعداد تست‌ها (گردشده به مضرب ۱۰)
- انتخاب سریع نام دانش‌آموز از لیست دکمه‌های شیشه‌ای یا تایپ نام جدید (با عنوان سربرگ «برنامه دکتر [نام]»)
- تقویم شمسی هوشمند به وقت ایران با گزینه‌های «شروع از امروز»، «شروع از فردا»، «شروع از شنبه آینده» و «تاریخ دلخواه»
- تولید فوری PDF اصلی برنامه مطالعاتی + گزینه اختیاری تولید فایل PDF جداگانه «وضعیت هفتگی» (اینفوگرافیک حرفه‌ای با فونت پینار)
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


class TelegramStudyPlanBot:
    def __init__(self, token: str, db_path: str = "consulting_bot.db") -> None:
        self.token = token
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.http = requests.Session()
        self.db = ConsultingDatabase(db_path)
        self.sessions: dict[int, dict] = {}
        # پیش‌بارگذاری فونت پینار و عکس‌های کاور در حافظه رم در لحظه استارت بات برای رندر آنی
        self._warm_up_assets()

    def _warm_up_assets(self) -> None:
        try:
            _get_cached_data_uri(ASSETS_DIR / "Pinar-Regular.ttf", "font/ttf")
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

    def edit_message_reply_markup(self, chat_id: int, message_id: int, reply_markup: dict) -> dict:
        return self._api(
            "editMessageReplyMarkup",
            data={
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
            },
        )

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self._api(
            "answerCallbackQuery",
            data={"callback_query_id": callback_id, "text": text},
        )

    def send_document(
        self, chat_id: int, file_path: Path, filename: str, caption: str = ""
    ) -> dict:
        with open(file_path, "rb") as f:
            return self._api(
                "sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                files={"document": (filename, f, "application/pdf")},
            )

    def _get_session(self, chat_id: int) -> dict:
        if chat_id not in self.sessions:
            self.sessions[chat_id] = {
                "state": "IDLE",
                "raw_chunks": [],
                "plan_data": None,
                "student_name": "",
                "include_summary": True,
                "send_weekly_status_pdf": True,
                "sync_weekdays": True,
            }
        return self.sessions[chat_id]

    def _build_student_selection_keyboard(self) -> dict:
        students = self.db.list_students_with_ids(limit=10)
        keyboard: list[list[dict]] = []
        row: list[dict] = []
        for item in students:
            row.append(
                {
                    "text": f"👤 {item['name']}",
                    "callback_data": f"stuid:{item['id']}",
                }
            )
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(
            [
                {"text": "➕ افزودن متن دیگر (ادامه برنامه)", "callback_data": "act:append_more"},
                {"text": "❌ لغو و شروع مجدد", "callback_data": "act:reset"},
            ]
        )
        return {"inline_keyboard": keyboard}

    def _build_date_selection_keyboard(self, session: dict) -> dict:
        plan_data = session.get("plan_data") or {}
        num_days = max(1, plan_data.get("summary", {}).get("num_days", 7))
        today = get_tehran_today()
        tomorrow = today + datetime.timedelta(days=1)
        next_sat = get_next_saturday(today)

        r_today = compute_plan_date_range(today, num_days)
        r_tmrw = compute_plan_date_range(tomorrow, num_days)
        r_sat = compute_plan_date_range(next_sat, num_days)

        status_icon = "✅" if session.get("send_weekly_status_pdf", True) else "⬜"
        sum_icon = "✅" if session.get("include_summary", True) else "⬜"
        sync_icon = "✅" if session.get("sync_weekdays", True) else "⬜"

        keyboard = [
            [
                {
                    "text": f"📅 از امروز ({r_today['start_full']} تا {r_today['end_full']})",
                    "callback_data": "date:today",
                }
            ],
            [
                {
                    "text": f"📆 از فردا ({r_tmrw['start_full']} تا {r_tmrw['end_full']})",
                    "callback_data": "date:tomorrow",
                }
            ],
            [
                {
                    "text": f"🗓 از شنبه آینده ({r_sat['start_full']} تا {r_sat['end_full']})",
                    "callback_data": "date:saturday",
                }
            ],
            [
                {
                    "text": "✏️ وارد کردن تاریخ دلخواه",
                    "callback_data": "date:custom",
                }
            ],
            [
                {
                    "text": f"{status_icon} ارسال PDF جداگانه «وضعیت هفتگی» (اینفوگرافیک)",
                    "callback_data": "toggle:weekly_status",
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
                {"text": "🔙 تغییر نام دانش‌آموز", "callback_data": "act:back_student"},
                {"text": "❌ لغو", "callback_data": "act:reset"},
            ],
        ]
        return {"inline_keyboard": keyboard}

    def _prompt_student_name(self, chat_id: int, session: dict) -> None:
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
                "لطفاً خروجی جدول برنامه‌ریزی جمینای را مستقیماً کپی و ارسال کنید.",
            )
            return

        session["state"] = "ASK_STUDENT"
        today_str = format_jalali_date(get_tehran_today(), include_weekday=True, include_year=True)

        msg = (
            f"✅ <b>برنامه مطالعاتی با موفقیت دریافت و آنالیز شد!</b>\n\n"
            f"📊 <b>تعداد روزهای تشخیص‌داده‌شده:</b> {to_persian_digits(num_days)} روز\n"
            f"⏱ <b>مجموع ساعات مطالعه:</b> {to_persian_digits(total_hours)} ساعت\n"
            f"📝 <b>مجموع تست‌ها (گردشده):</b> حدود {to_persian_digits(total_tests)} تست\n"
            f"📅 <b>تاریخ امروز:</b> {today_str}\n\n"
            f"👤 <b>لطفاً نام دانش‌آموز را تایپ کنید</b> (مثلاً <i>نرگس</i>، <i>خانم علیپور</i>، یا از دکمه‌های زیر انتخاب نمایید):\n"
            f"<i>💡 در سربرگ برنامه به صورت خودکار «برنامه دکتر [نام]» درج خواهد شد.</i>"
        )
        self.send_message(
            chat_id,
            msg,
            reply_markup=self._build_student_selection_keyboard(),
        )

    def _prompt_date_choice(self, chat_id: int, session: dict) -> None:
        session["state"] = "ASK_DATE"
        student = session["student_name"]
        header_preview = format_doctor_student_title(student)
        num_days = session["plan_data"]["summary"]["num_days"]
        today_str = format_jalali_date(get_tehran_today(), include_weekday=True, include_year=True)

        msg = (
            f"👤 <b>دانش‌آموز:</b> {student}\n"
            f"🏷 <b>عنوان سربرگ:</b> {header_preview}\n"
            f"📆 <b>طول برنامه:</b> {to_persian_digits(num_days)} روزه\n"
            f"🕒 <b>امروز به شمسی:</b> {today_str}\n\n"
            f"👇 <b>برنامه از چه روزی شروع می‌شود؟</b>\n"
            f"<i>می‌توانید تیک «ارسال PDF جداگانه وضعیت هفتگی» را هم روشن یا خاموش کنید:</i>"
        )
        self.send_message(
            chat_id,
            msg,
            reply_markup=self._build_date_selection_keyboard(session),
        )

    def _finalize_and_send_pdf(
        self, chat_id: int, session: dict, date_info: dict
    ) -> None:
        student = session["student_name"].strip()
        plan_data = session["plan_data"]
        num_days = plan_data["summary"]["num_days"]
        total_hours = plan_data["summary"]["total_hours"]
        want_status_pdf = session.get("send_weekly_status_pdf", True)

        self.send_message(
            chat_id,
            f"⚡ <b>در حال رندر فوری خروجی برای «{format_doctor_student_title(student)}»...</b>",
        )

        safe_slug = student.replace(" ", "_").replace("/", "-")
        range_slug = to_persian_digits(date_info["short_range"]).replace(" ", "_")
        main_pdf_filename = f"برنامه_مطالعاتی_{safe_slug}_{range_slug}.pdf"
        status_pdf_filename = f"وضعیت_هفتگی_{safe_slug}_{range_slug}.pdf"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_main = tmp_path / main_pdf_filename
            t0 = time.time()
            generate_study_plan_pdf(
                plan_data=plan_data,
                student_name=student,
                date_info=date_info,
                output_path=out_main,
                assets_dir=ASSETS_DIR,
                include_summary=session.get("include_summary", True),
                sync_weekday_names=session.get("sync_weekdays", True),
            )
            elapsed_main = round(time.time() - t0, 2)

            caption_main = (
                f"🎓 <b>{format_doctor_student_title(student)}</b>\n"
                f"📅 <b>بازه برنامه:</b> {date_info['start_full']} تا {date_info['end_full']} ({to_persian_digits(num_days)} روزه)\n"
                f"⏱ <b>مجموع مطالعه:</b> {to_persian_digits(total_hours)} ساعت\n"
                f"⚡ <b>زمان رندر:</b> {to_persian_digits(elapsed_main)} ثانیه با فونت پینار"
            )
            self.send_document(chat_id, out_main, main_pdf_filename, caption=caption_main)

            if want_status_pdf:
                out_status = tmp_path / status_pdf_filename
                t1 = time.time()
                generate_weekly_status_pdf(
                    plan_data=plan_data,
                    student_name=student,
                    date_info=date_info,
                    output_path=out_status,
                    assets_dir=ASSETS_DIR,
                )
                elapsed_status = round(time.time() - t1, 2)
                caption_status = (
                    f"📊 <b>وضعیت هفتگی (اینفوگرافیک): {format_doctor_student_title(student)}</b>\n"
                    f"📅 <b>بازه:</b> {date_info['short_range']}\n"
                    f"⚡ <b>زمان رندر:</b> {to_persian_digits(elapsed_status)} ثانیه با فونت پینار"
                )
                self.send_document(
                    chat_id, out_status, status_pdf_filename, caption=caption_status
                )

        self.db.add_or_touch_student(student)
        self.db.log_plan(student, date_info["short_range"], num_days, total_hours)
        session["state"] = "IDLE"
        session["raw_chunks"] = []
        session["plan_data"] = None

    def handle_message(self, message: dict) -> None:
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if "document" in message and not text:
            doc = message["document"]
            fname = doc.get("file_name", "")
            if fname.endswith(".txt") or fname.endswith(".md"):
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
                f"به ربات <b>تبدیل فوق‌سریع برنامه مطالعاتی به PDF و اینفوگرافیک وضعیت هفتگی (با فونت پینار)</b> خوش آمدید.\n\n"
                f"📅 <b>تاریخ امروز:</b> {today_str}\n\n"
                f"🚀 <b>نحوه استفاده:</b>\n"
                f"۱. متن جدول برنامه مطالعاتی که از <b>جمینای (Gemini)</b> گرفته‌اید را کپی کرده و بفرستید.\n"
                f"۲. نام دانش‌آموز را انتخاب یا تایپ کنید (در سربرگ به صورت <b>برنامه دکتر [نام]</b> درج می‌شود).\n"
                f"۳. تاریخ شروع (از امروز / از فردا / شنبه آینده) را بزنید تا هم <b>PDF برنامه مطالعاتی</b> و هم در صورت انتخاب، <b>PDF جداگانه وضعیت هفتگی (اینفوگرافیک)</b> در کسری از ثانیه ارسال شود!"
            )
            self.send_message(chat_id, welcome)
            return

        if text.startswith("/students"):
            students = self.db.list_students(limit=20)
            if not students:
                self.send_message(chat_id, "📭 هنوز دانش‌آموزی در لیست ذخیره نشده است.")
            else:
                items = "\n".join(f"• {s}" for s in students)
                self.send_message(chat_id, f"👥 <b>لیست دانش‌آموزان ذخیره‌شده:</b>\n\n{items}")
            return

        looks_like_plan = ("پارت" in text and "درس" in text) or ("ساعت شروع" in text) or ("روز اول" in text)

        if session["state"] in ("IDLE", "WAIT_MORE_TEXT") or (
            session["state"] == "ASK_STUDENT" and looks_like_plan and len(text) > 80
        ):
            session["raw_chunks"].append(text)
            self._prompt_student_name(chat_id, session)
            return

        if session["state"] == "ASK_STUDENT":
            session["student_name"] = text.strip()
            self._prompt_date_choice(chat_id, session)
            return

        if session["state"] == "ASK_CUSTOM_DATE":
            num_days = session["plan_data"]["summary"]["num_days"]
            custom_text = to_persian_digits(text.strip())
            date_info = {
                "num_days": num_days,
                "short_range": custom_text,
                "start_full": custom_text,
                "end_full": "",
            }
            self._finalize_and_send_pdf(chat_id, session, date_info)
            return

        if looks_like_plan:
            session["raw_chunks"] = [text]
            self._prompt_student_name(chat_id, session)
        else:
            self.send_message(
                chat_id,
                "📋 لطفاً ابتدا متن جدول برنامه مطالعاتی را ارسال کنید.",
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
            self.send_message(chat_id, "🔄 عملیات لغو شد. هر زمان آماده بودید متن برنامه جدید را بفرستید.")
            return

        if data == "act:append_more":
            session["state"] = "WAIT_MORE_TEXT"
            self.send_message(
                chat_id,
                "➕ <b>لطفاً بخش بعدی متن جدول را ارسال کنید</b> تا به روزهای قبلی اضافه شود:",
            )
            return

        if data == "act:back_student":
            self._prompt_student_name(chat_id, session)
            return

        if data.startswith("stuid:"):
            stu_id = int(data.split(":", 1)[1])
            student_name = self.db.get_student_by_id(stu_id) or "دانش‌آموز"
            session["student_name"] = student_name
            self._prompt_date_choice(chat_id, session)
            return

        if data in ("toggle:weekly_status", "toggle:summary", "toggle:sync"):
            if data == "toggle:weekly_status":
                session["send_weekly_status_pdf"] = not session.get(
                    "send_weekly_status_pdf", True
                )
            elif data == "toggle:summary":
                session["include_summary"] = not session.get("include_summary", True)
            elif data == "toggle:sync":
                session["sync_weekdays"] = not session.get("sync_weekdays", True)

            if msg_id:
                self.edit_message_reply_markup(
                    chat_id, msg_id, self._build_date_selection_keyboard(session)
                )
            else:
                self._prompt_date_choice(chat_id, session)
            return

        if data.startswith("date:"):
            if not session.get("plan_data"):
                self.send_message(chat_id, "⚠️ ابتدا متن برنامه را ارسال کنید.")
                return
            choice = data.split(":", 1)[1]
            num_days = max(1, session["plan_data"]["summary"]["num_days"])
            today = get_tehran_today()

            if choice == "today":
                date_info = compute_plan_date_range(today, num_days)
                self._finalize_and_send_pdf(chat_id, session, date_info)
            elif choice == "tomorrow":
                tmrw = today + datetime.timedelta(days=1)
                date_info = compute_plan_date_range(tmrw, num_days)
                self._finalize_and_send_pdf(chat_id, session, date_info)
            elif choice == "saturday":
                sat = get_next_saturday(today)
                date_info = compute_plan_date_range(sat, num_days)
                self._finalize_and_send_pdf(chat_id, session, date_info)
            elif choice == "custom":
                session["state"] = "ASK_CUSTOM_DATE"
                self.send_message(
                    chat_id,
                    "✏️ <b>لطفاً بازه تاریخ مورد نظر خود را تایپ کنید:</b>\n"
                    "<i>مثال: دوشنبه ۴ آبان تا یکشنبه ۱۰ آبان</i>",
                )

    def run_polling(self) -> None:
        logger.info("Starting @DRpdfmakerbot v2 polling loop...")
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
