# -*- coding: utf-8 -*-
"""
موتور فوق‌سریع تولید فایل‌های PDF برنامه مطالعاتی دکتر هاشمی با فونت پینار (Pinar-Regular.ttf):
۱. generate_study_plan_pdf: تولید برنامه مطالعاتی اصلی (کاور اختصاصی بدون متن تمرکز، سربرگ گرادینت با نام «برنامه دکتر [نام]» رنگی و وسط‌چین، جداول ۶ رنگ، و جدول خلاصه انتهایی با ساعت خالص و تست‌های گردشده به مضرب ۱۰).
۲. generate_weekly_status_pdf: تولید فایل PDF جداگانه «وضعیت هفتگی» (اینفوگرافیک حرفه‌ای مشابه code_artifact (1).html با کاور صفحه اول، سربرگ برنامه و داشبورد تاریک مدرن با فونت پینار).
"""

from __future__ import annotations
import base64
import html
from pathlib import Path
import weasyprint
from weasyprint.text.fonts import FontConfiguration

from src.jalali import to_persian_digits
from src.parser import (
    compute_column_percentages,
    format_doctor_student_title,
    format_hours_clean,
    round_to_nearest_10,
    ORDINAL_DAYS as PARSER_ORDINAL_DAYS,
)

# کش سراسری در حافظه رم برای حذف خواندن تکراری دیسک و افزایش چشمگیر سرعت رندرینگ
_ASSET_URI_CACHE: dict[str, str] = {}
_SHARED_FONT_CONFIG = FontConfiguration()

# ۶ استایل رنگی دقیقاً مطابق با Grid Table 4 - Accent 1..6 در فایل Word کاربر
TABLE_ACCENT_STYLES = [
    {
        "name": "Accent 1 (Blue)",
        "header_bg": "#4472C4",
        "header_text": "#FFFFFF",
        "even_bg": "#D9E2F3",
        "odd_bg": "#FFFFFF",
        "border": "#8EA9DB",
    },
    {
        "name": "Accent 2 (Orange)",
        "header_bg": "#ED7D31",
        "header_text": "#FFFFFF",
        "even_bg": "#FCE4D6",
        "odd_bg": "#FFFFFF",
        "border": "#F4B083",
    },
    {
        "name": "Accent 3 (Grey)",
        "header_bg": "#A5A5A5",
        "header_text": "#FFFFFF",
        "even_bg": "#EDEDED",
        "odd_bg": "#FFFFFF",
        "border": "#C9C9C9",
    },
    {
        "name": "Accent 4 (Gold/Yellow)",
        "header_bg": "#FFC000",
        "header_text": "#FFFFFF",
        "even_bg": "#FFF2CC",
        "odd_bg": "#FFFFFF",
        "border": "#FFD965",
    },
    {
        "name": "Accent 5 (Light Blue)",
        "header_bg": "#5B9BD5",
        "header_text": "#FFFFFF",
        "even_bg": "#DEEBF6",
        "odd_bg": "#FFFFFF",
        "border": "#9CC2E5",
    },
    {
        "name": "Accent 6 (Green)",
        "header_bg": "#70AD47",
        "header_text": "#FFFFFF",
        "even_bg": "#E2EFDA",
        "odd_bg": "#FFFFFF",
        "border": "#A8D08D",
    },
]

# پالت رنگی دروس در اینفوگرافیک وضعیت هفتگی (مشابه code_artifact (1).html)
SUBJECT_THEMES = [
    {"text": "#34D399", "bg": "#10B981", "badge_bg": "rgba(16, 185, 129, 0.16)", "border": "#10B981"},  # Emerald
    {"text": "#38BDF8", "bg": "#0EA5E9", "badge_bg": "rgba(14, 165, 233, 0.16)", "border": "#0EA5E9"},  # Sky
    {"text": "#FBBF24", "bg": "#F59E0B", "badge_bg": "rgba(245, 158, 11, 0.16)", "border": "#F59E0B"},  # Amber
    {"text": "#C084FC", "bg": "#A855F7", "badge_bg": "rgba(168, 85, 247, 0.16)", "border": "#A855F7"},  # Purple
    {"text": "#2DD4BF", "bg": "#14B8A6", "badge_bg": "rgba(20, 184, 166, 0.16)", "border": "#14B8A6"},  # Teal
]


def _get_cached_data_uri(path: Path, mime: str) -> str:
    key = str(path.resolve())
    if key not in _ASSET_URI_CACHE:
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        _ASSET_URI_CACHE[key] = f"data:{mime};base64,{b64}"
    return _ASSET_URI_CACHE[key]


def _enrich_day_title_with_date(raw_title: str, day_idx: int, date_info: dict | None) -> str:
    if not date_info or "daily_dates" not in date_info:
        return to_persian_digits(raw_title)
    daily_list = date_info["daily_dates"]
    if day_idx >= len(daily_list):
        return to_persian_digits(raw_title)

    d_item = daily_list[day_idx]
    ord_word = (
        PARSER_ORDINAL_DAYS[day_idx]
        if day_idx < len(PARSER_ORDINAL_DAYS)
        else to_persian_digits(day_idx + 1)
    )
    return f"روز {ord_word} - {d_item['full_label']}"


def build_study_plan_html(
    plan_data: dict,
    student_name: str,
    date_info: dict,
    assets_dir: Path,
    include_summary: bool = True,
    sync_weekday_names: bool = True,
) -> str:
    """ساخت کد HTML/CSS برنامه مطالعاتی اصلی با تمام اصلاحات نسخه ۲."""
    font_uri = _get_cached_data_uri(assets_dir / "Pinar-Regular.ttf", "font/ttf")
    cover_uri = _get_cached_data_uri(assets_dir / "cover_bg.jpg", "image/jpeg")
    cal_uri = _get_cached_data_uri(assets_dir / "calendar_icon.png", "image/png")

    safe_student = html.escape(to_persian_digits(student_name.strip()))
    doctor_student_header = html.escape(format_doctor_student_title(student_name))
    short_range = html.escape(date_info.get("short_range", ""))
    start_full = html.escape(date_info.get("start_full", ""))
    end_full = html.escape(date_info.get("end_full", ""))

    # خط دوم باکس روی کاور: بدون بخش «تمرکز: پیشروی + تسلط حداکثری»
    if end_full and not end_full.startswith("برنامه"):
        cover_line_2 = f"شروع برنامه: {start_full} تا {end_full}"
    else:
        cover_line_2 = f"شروع برنامه: {start_full}"

    days = plan_data.get("days", [])
    days_html_parts: list[str] = []

    for idx, day in enumerate(days):
        accent = TABLE_ACCENT_STYLES[idx % 6]
        headers = day.get("headers", [])
        col_pcts = compute_column_percentages(headers)

        if sync_weekday_names and date_info:
            day_title = _enrich_day_title_with_date(day.get("title", ""), idx, date_info)
        else:
            day_title = to_persian_digits(day.get("title", f"روز {idx + 1}"))

        start_time = html.escape(to_persian_digits(day.get("start_time", "۸:۱۵")))
        total_hours = html.escape(to_persian_digits(day.get("total_hours", "")))

        colgroup_html = "".join(f'<col style="width: {pct}%;" />' for pct in col_pcts)
        ths_html = "".join(
            f'<th style="background-color: {accent["header_bg"]}; color: {accent["header_text"]}; border: 1px solid {accent["border"]};">{html.escape(h)}</th>'
            for h in headers
        )

        rows_html_list: list[str] = []
        for r_idx, row in enumerate(day.get("rows", [])):
            row_bg = accent["even_bg"] if (r_idx % 2 == 0) else accent["odd_bg"]
            tds = "".join(
                f'<td style="background-color: {row_bg}; border: 1px solid {accent["border"]};">{html.escape(str(cell))}</td>'
                for cell in row
            )
            rows_html_list.append(f"<tr>{tds}</tr>")

        rows_html = "\n".join(rows_html_list)

        day_block = f"""
        <div class="day-section">
          <div class="day-meta">
            <div class="day-title">{html.escape(day_title)}</div>
            <div class="day-start">ساعت شروع: {start_time}</div>
          </div>
          <table class="study-table">
            <colgroup>{colgroup_html}</colgroup>
            <thead>
              <tr>{ths_html}</tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
          <div class="day-total">{total_hours}</div>
        </div>
        """
        days_html_parts.append(day_block)

    # جدول انتهای برنامه:
    # - بدون خط‌چین و بدون تیتر «خلاصه آماری برنامه (۷ روزه)»
    # - نگه داشتن خط «مجموع کل مطالعه: ... ساعت | مجموع کل تست: ... تست»
    # - نمایش ساعت مطالعه هر درس فقط به ساعت (بدون دقیقه)
    # - گرد کردن اعداد تست به مضرب ۱۰
    summary_html = ""
    summary = plan_data.get("summary", {})
    if include_summary and summary.get("total_minutes", 0) > 0:
        tot_hrs_fa = to_persian_digits(f"{summary['total_hours']:g}")
        tot_tests_fa = to_persian_digits(round_to_nearest_10(summary.get("total_tests", 0)))
        subj_mins: dict[str, int] = summary.get("subject_minutes", {})
        subj_tests: dict[str, int] = summary.get("subject_tests", {})

        subj_rows = []
        for s_idx, (subj_name, mins) in enumerate(
            sorted(subj_mins.items(), key=lambda x: x[1], reverse=True)
        ):
            hrs_fa = f"{format_hours_clean(mins)} ساعت"
            tst_rounded = round_to_nearest_10(subj_tests.get(subj_name, 0))
            tst_fa = to_persian_digits(tst_rounded)
            bg = "#E2EFDA" if s_idx % 2 == 0 else "#FFFFFF"
            subj_rows.append(
                f'<tr>'
                f'<td style="background:{bg}; border:1px solid #A8D08D; font-weight:bold;">{html.escape(subj_name)}</td>'
                f'<td style="background:{bg}; border:1px solid #A8D08D;">{hrs_fa}</td>'
                f'<td style="background:{bg}; border:1px solid #A8D08D;">{tst_fa} تست</td>'
                f'</tr>'
            )

        summary_html = f"""
        <div class="day-section summary-box">
          <div class="day-meta">
            <div class="day-start" style="font-weight: bold; font-size: 9.2pt; color: #1A1A1A; margin-bottom: 5px;">
              مجموع کل مطالعه: {tot_hrs_fa} ساعت | مجموع کل تست: {tot_tests_fa} تست
            </div>
          </div>
          <table class="study-table">
            <colgroup>
              <col style="width: 34%;" />
              <col style="width: 38%;" />
              <col style="width: 28%;" />
            </colgroup>
            <thead>
              <tr>
                <th style="background-color:#0070C0; color:#FFFFFF; border:1px solid #0070C0;">نام درس</th>
                <th style="background-color:#0070C0; color:#FFFFFF; border:1px solid #0070C0;">مجموع زمان مطالعه</th>
                <th style="background-color:#0070C0; color:#FFFFFF; border:1px solid #0070C0;">مجموع تعداد تست</th>
              </tr>
            </thead>
            <tbody>
              {"".join(subj_rows)}
            </tbody>
          </table>
        </div>
        """

    html_doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <style>
    @font-face {{
      font-family: 'Pinar';
      src: url('{font_uri}') format('truetype');
      font-weight: normal;
      font-style: normal;
    }}
    @font-face {{
      font-family: 'Pinar';
      src: url('{font_uri}') format('truetype');
      font-weight: bold;
      font-style: normal;
    }}

    @page {{
      size: A4 portrait;
      margin: 26mm 8mm 16mm 8mm;
      @top-center {{
        content: element(running-header);
        width: 100%;
      }}
      @bottom-center {{
        content: element(running-footer);
        width: 100%;
      }}
    }}

    @page :first {{
      margin: 0mm;
      @top-center {{ content: none; }}
      @bottom-center {{ content: none; }}
    }}

    * {{
      box-sizing: border-box;
      font-family: 'Pinar', sans-serif;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      direction: rtl;
      text-align: right;
      color: #1A1A1A;
      font-size: 9.5pt;
      line-height: 1.45;
    }}

    /* ۱. صفحه اول (کاور اختصاصی دکتر هاشمی + باکس مشخصات پایین کاور) */
    .cover-page {{
      position: relative;
      width: 210mm;
      height: 297mm;
      overflow: hidden;
      page-break-after: always;
      break-after: page;
    }}

    .cover-bg {{
      position: absolute;
      top: 0;
      left: 0;
      width: 210mm;
      height: 297mm;
      object-fit: cover;
      z-index: 1;
    }}

    .cover-badge-box {{
      position: absolute;
      bottom: 14mm;
      left: 15mm;
      right: 15mm;
      background-color: rgba(255, 255, 255, 0.97);
      border: 2.5px solid #0070C0;
      border-radius: 14px;
      padding: 12px 18px;
      text-align: center;
      z-index: 5;
      box-shadow: 0 4px 14px rgba(0, 50, 100, 0.15);
    }}

    .cover-badge-title {{
      font-size: 16.5pt;
      font-weight: bold;
      color: #06396B;
      margin-bottom: 5px;
      line-height: 1.35;
    }}

    .cover-badge-subtitle {{
      font-size: 11pt;
      font-weight: bold;
      color: #D9531E;
      line-height: 1.35;
    }}

    /* ۲. سربرگ گرادینت با فونت بزرگ‌تر، رنگی و کاملاً وسط‌چین در هر دو سمت */
    .running-header {{
      position: running(running-header);
      width: 194mm;
      margin: 0 auto;
      padding-top: 3mm;
    }}

    .header-banner {{
      width: 194mm;
      height: 15mm;
      border-radius: 9px;
      background: linear-gradient(90deg, #4B9CD3 0%, #3BB29B 50%, #5ECF95 100%);
      border-collapse: collapse;
      table-layout: fixed;
    }}

    .header-side {{
      width: 81mm;
      vertical-align: middle;
      text-align: center;
      padding: 0 4mm;
    }}

    .header-student-pill {{
      font-size: 11.8pt;
      font-weight: bold;
      color: #FFF799;
      text-shadow: 0 1px 3px rgba(6, 40, 75, 0.6);
      white-space: nowrap;
    }}

    .header-date-pill {{
      font-size: 11pt;
      font-weight: bold;
      color: #FFFFFF;
      text-shadow: 0 1px 3px rgba(6, 40, 75, 0.5);
      white-space: nowrap;
    }}

    .header-center {{
      width: 32mm;
      vertical-align: middle;
      text-align: center;
    }}

    .header-center img {{
      height: 14.2mm;
      width: auto;
      display: block;
      margin: 0 auto;
    }}

    .running-footer {{
      position: running(running-footer);
      width: 100%;
      text-align: center;
      font-size: 9.5pt;
      color: #7F7F7F;
      padding-bottom: 2mm;
      direction: ltr;
    }}

    /* ۳. استایل بخش‌های روزانه و جدول‌ها */
    .day-section {{
      margin-bottom: 10px;
      page-break-inside: avoid;
      break-inside: avoid;
    }}

    .day-meta {{
      margin-bottom: 4px;
      text-align: right;
    }}

    .day-title {{
      font-size: 10pt;
      font-weight: bold;
      color: #111111;
      margin-bottom: 1px;
    }}

    .day-start {{
      font-size: 8.5pt;
      color: #333333;
      margin-bottom: 3px;
    }}

    .study-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-bottom: 4px;
    }}

    .study-table th {{
      font-size: 8.8pt;
      font-weight: bold;
      text-align: center;
      vertical-align: middle;
      padding: 5px 4px;
      line-height: 1.3;
    }}

    .study-table td {{
      font-size: 8.5pt;
      text-align: center;
      vertical-align: middle;
      padding: 5px 4px;
      line-height: 1.35;
      color: #111111;
      word-wrap: break-word;
    }}

    .day-total {{
      font-size: 8.8pt;
      font-weight: bold;
      color: #111111;
      text-align: right;
      margin-top: 2px;
      margin-bottom: 6px;
    }}

    .summary-box {{
      margin-top: 10px;
      padding-top: 4px;
    }}
  </style>
</head>
<body>
  <!-- صفحه اول: کاور اختصاصی دکتر هاشمی به همراه باکس مشخصات -->
  <div class="cover-page">
    <img class="cover-bg" src="{cover_uri}" alt="Cover" />
    <div class="cover-badge-box">
      <div class="cover-badge-title">برنامه هفتگی اختصاصی: {safe_student}</div>
      <div class="cover-badge-subtitle">{cover_line_2}</div>
    </div>
  </div>

  <!-- سربرگ تکرارشونده صفحات داخلی -->
  <div class="running-header">
    <table class="header-banner">
      <tr>
        <td class="header-side">
          <span class="header-student-pill">{doctor_student_header}</span>
        </td>
        <td class="header-center">
          <img src="{cal_uri}" alt="Calendar" />
        </td>
        <td class="header-side">
          <span class="header-date-pill">{short_range}</span>
        </td>
      </tr>
    </table>
  </div>

  <!-- پاورقی تکرارشونده صفحات داخلی -->
  <div class="running-footer">
    The only easy day was yesterday!
  </div>

  <!-- محتوای جداول روزانه -->
  <main>
    {"".join(days_html_parts)}
    {summary_html}
  </main>
</body>
</html>
"""
    return html_doc


def build_weekly_status_html(
    plan_data: dict,
    student_name: str,
    date_info: dict,
    assets_dir: Path,
) -> str:
    """
    ساخت HTML/CSS فایل PDF جداگانه «وضعیت هفتگی» (اینفوگرافیک برنامه مطالعاتی):
    - صفحه اول: کاور اختصاصی دکتر هاشمی + باکس مشخصات پایین کاور
    - صفحه دوم: سربرگ گرادینت (برنامه دکتر [نام] + تاریخ) و داشبورد اینفوگرافیک فوق‌حرفه‌ای
      دقیقاً مطابق با طراحی code_artifact (1).html و با فونت پینار.
    """
    font_uri = _get_cached_data_uri(assets_dir / "Pinar-Regular.ttf", "font/ttf")
    cover_uri = _get_cached_data_uri(assets_dir / "cover_bg.jpg", "image/jpeg")
    cal_uri = _get_cached_data_uri(assets_dir / "calendar_icon.png", "image/png")

    safe_student = html.escape(to_persian_digits(student_name.strip()))
    doctor_student_header = html.escape(format_doctor_student_title(student_name))
    short_range = html.escape(date_info.get("short_range", ""))
    start_full = html.escape(date_info.get("start_full", ""))
    end_full = html.escape(date_info.get("end_full", ""))

    if end_full and not end_full.startswith("برنامه"):
        cover_line_2 = f"شروع برنامه: {start_full} تا {end_full}"
    else:
        cover_line_2 = f"شروع برنامه: {start_full}"

    summary = plan_data.get("summary", {})
    total_mins = summary.get("total_minutes", 0)
    total_hrs_clean = format_hours_clean(total_mins)
    hrs_int = total_mins // 60
    rem_mins = total_mins % 60
    if rem_mins > 0:
        total_hrs_verbose = f"{to_persian_digits(hrs_int)} ساعت و {to_persian_digits(rem_mins)} دقیقه"
    else:
        total_hrs_verbose = f"{to_persian_digits(hrs_int)} ساعت"

    avg_hrs_fa = to_persian_digits(f"{summary.get('avg_daily_hours', 0):g}")
    total_parts_fa = to_persian_digits(summary.get("total_parts", 0))

    # هدف‌گذاری تعداد تست به صورت بازه مضرب ۱۰ (مثلاً ۲۵۰ تا ۲۷۰ تست)
    rounded_tests = round_to_nearest_10(summary.get("total_tests", 0))
    low_t = max(10, rounded_tests - 10)
    high_t = rounded_tests + 10
    test_range_fa = f"{to_persian_digits(low_t)} تا {to_persian_digits(high_t)} تست"

    # آمار انواع پارت (آموزش، تسلط، مرور)
    pt_mins = summary.get("part_type_minutes", {"آموزش": 0, "تسلط": 0, "مرور": 0})
    pt_counts = summary.get("part_type_counts", {"آموزش": 0, "تسلط": 0, "مرور": 0})

    learn_mins = pt_mins.get("آموزش", 0)
    master_mins = pt_mins.get("تسلط", 0)
    review_mins = pt_mins.get("مرور", 0)

    denom = max(1, learn_mins + master_mins + review_mins)
    learn_pct = round((learn_mins / denom) * 100)
    master_pct = round((master_mins / denom) * 100)
    review_pct = max(0, 100 - learn_pct - master_pct)

    learn_hrs_fa = format_hours_clean(learn_mins)
    master_hrs_fa = format_hours_clean(master_mins)
    review_hrs_fa = format_hours_clean(review_mins)

    learn_cnt_fa = to_persian_digits(pt_counts.get("آموزش", 0))
    master_cnt_fa = to_persian_digits(pt_counts.get("تسلط", 0))
    review_cnt_fa = to_persian_digits(pt_counts.get("مرور", 0))

    # لیست دروس مرتب‌شده بر اساس زمان مطالعه
    subj_mins: dict[str, int] = summary.get("subject_minutes", {})
    subj_tests: dict[str, int] = summary.get("subject_tests", {})
    subj_topics: dict[str, list[str]] = summary.get("subject_topics", {})
    sorted_subjects = sorted(subj_mins.items(), key=lambda x: x[1], reverse=True)

    subject_progress_rows = []
    for idx, (s_name, s_min) in enumerate(sorted_subjects[:6]):
        theme = SUBJECT_THEMES[idx % len(SUBJECT_THEMES)]
        pct = round((s_min / max(1, total_mins)) * 100, 1)
        pct_fa = to_persian_digits(f"{pct:g}")
        s_hrs_fa = format_hours_clean(s_min)
        s_tst_fa = to_persian_digits(round_to_nearest_10(subj_tests.get(s_name, 0)))
        rank_fa = to_persian_digits(idx + 1)

        subject_progress_rows.append(
            f"""
            <div class="subj-row">
              <table class="subj-row-tbl">
                <tr>
                  <td style="text-align:right; color:{theme['text']}; font-weight:bold;">
                    {rank_fa}. {html.escape(s_name)} ({pct_fa}٪ برنامه)
                  </td>
                  <td style="text-align:left; color:#E2E8F0; font-weight:bold;">
                    {s_hrs_fa} ساعت | {s_tst_fa} تست
                  </td>
                </tr>
              </table>
              <div class="prog-track">
                <div class="prog-fill" style="width: {max(6, min(100, pct))}%; background-color: {theme['bg']};"></div>
              </div>
            </div>
            """
        )

    # نمودار روند ساعت مطالعه روزانه
    daily_stats = summary.get("daily_stats", [])
    max_day_hrs = max([d.get("hours", 1.0) for d in daily_stats] + [8.0])
    bar_cols_html = []
    for d_idx, d_stat in enumerate(daily_stats):
        h_val = d_stat.get("hours", 0.0)
        bar_px = int(round((h_val / max_day_hrs) * 105))
        bar_px = max(18, min(115, bar_px))
        bar_color = "#38BDF8" if d_idx < 4 else ("#818CF8" if d_idx < 6 else "#34D399")

        bar_cols_html.append(
            f"""
            <td class="chart-col">
              <div class="bar-num" style="color: {bar_color};">{html.escape(d_stat.get('hours_fa', ''))}</div>
              <div class="bar-pillar" style="height: {bar_px}px; background: {bar_color};"></div>
            </td>
            """
        )

    bar_days_html = []
    for d_idx, d_stat in enumerate(daily_stats):
        day_label = d_stat.get("label", "")
        if date_info and "daily_dates" in date_info and d_idx < len(date_info["daily_dates"]):
            day_label = date_info["daily_dates"][d_idx]["weekday"]
        bar_days_html.append(f'<td class="bar-day">{html.escape(day_label)}</td>')

    # کارت‌های مباحث دروس در پایین صفحه
    topic_cards_html = []
    for idx, (s_name, s_min) in enumerate(sorted_subjects[:5]):
        theme = SUBJECT_THEMES[idx % len(SUBJECT_THEMES)]
        s_hrs_fa = format_hours_clean(s_min)
        topics = subj_topics.get(s_name, [])[:5]
        li_items = "".join(
            f"""
            <div class="topic-pill">
              <span class="topic-dot" style="background-color: {theme['text']};"></span>
              <span>{html.escape(tp)}</span>
            </div>
            """
            for tp in topics
        )
        topic_cards_html.append(
            f"""
            <td class="topic-card-cell">
              <div class="topic-card" style="border-top: 3.5px solid {theme['border']};">
                <table class="topic-card-hdr-tbl">
                  <tr>
                    <td style="text-align:right; width:58%;">
                      <span class="topic-card-title" style="color: {theme['text']};">{html.escape(s_name)}</span>
                    </td>
                    <td style="text-align:left; width:42%;">
                      <span class="topic-card-badge" style="background: {theme['badge_bg']}; color: {theme['text']};">{s_hrs_fa} ساعت</span>
                    </td>
                  </tr>
                </table>
                <div class="topic-list">
                  {li_items}
                </div>
              </div>
            </td>
            """
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <style>
    @font-face {{
      font-family: 'Pinar';
      src: url('{font_uri}') format('truetype');
      font-weight: normal;
      font-style: normal;
    }}
    @font-face {{
      font-family: 'Pinar';
      src: url('{font_uri}') format('truetype');
      font-weight: bold;
      font-style: normal;
    }}

    @page {{
      size: A4 portrait;
      margin: 24mm 7mm 14mm 7mm;
      background-color: #090D16;
      @top-center {{
        content: element(running-header);
        width: 100%;
      }}
      @bottom-center {{
        content: element(running-footer);
        width: 100%;
      }}
    }}

    @page :first {{
      margin: 0mm;
      background-color: #FFFFFF;
      @top-center {{ content: none; }}
      @bottom-center {{ content: none; }}
    }}

    * {{
      box-sizing: border-box;
      font-family: 'Pinar', sans-serif;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      direction: rtl;
      text-align: right;
      color: #F8FAFC;
      font-size: 9pt;
    }}

    /* صفحه اول: کاور */
    .cover-page {{
      position: relative;
      width: 210mm;
      height: 297mm;
      overflow: hidden;
      page-break-after: always;
      break-after: page;
      background: #FFFFFF;
    }}

    .cover-bg {{
      position: absolute;
      top: 0;
      left: 0;
      width: 210mm;
      height: 297mm;
      object-fit: cover;
      z-index: 1;
    }}

    .cover-badge-box {{
      position: absolute;
      bottom: 14mm;
      left: 15mm;
      right: 15mm;
      background-color: rgba(255, 255, 255, 0.97);
      border: 2.5px solid #0070C0;
      border-radius: 14px;
      padding: 12px 18px;
      text-align: center;
      z-index: 5;
      box-shadow: 0 4px 14px rgba(0, 50, 100, 0.15);
    }}

    .cover-badge-title {{
      font-size: 16.5pt;
      font-weight: bold;
      color: #06396B;
      margin-bottom: 5px;
      line-height: 1.35;
    }}

    .cover-badge-subtitle {{
      font-size: 11pt;
      font-weight: bold;
      color: #D9531E;
      line-height: 1.35;
    }}

    /* سربرگ گرادینت در صفحه وضعیت هفتگی */
    .running-header {{
      position: running(running-header);
      width: 196mm;
      margin: 0 auto;
      padding-top: 3mm;
    }}

    .header-banner {{
      width: 196mm;
      height: 15mm;
      border-radius: 9px;
      background: linear-gradient(90deg, #4B9CD3 0%, #3BB29B 50%, #5ECF95 100%);
      border-collapse: collapse;
      table-layout: fixed;
    }}

    .header-side {{
      width: 82mm;
      vertical-align: middle;
      text-align: center;
      padding: 0 4mm;
    }}

    .header-student-pill {{
      font-size: 11.8pt;
      font-weight: bold;
      color: #FFF799;
      text-shadow: 0 1px 3px rgba(6, 40, 75, 0.6);
      white-space: nowrap;
    }}

    .header-date-pill {{
      font-size: 11pt;
      font-weight: bold;
      color: #FFFFFF;
      text-shadow: 0 1px 3px rgba(6, 40, 75, 0.5);
      white-space: nowrap;
    }}

    .header-center {{
      width: 32mm;
      vertical-align: middle;
      text-align: center;
    }}

    .header-center img {{
      height: 14.2mm;
      width: auto;
      display: block;
      margin: 0 auto;
    }}

    .running-footer {{
      position: running(running-footer);
      width: 100%;
      text-align: center;
      font-size: 9pt;
      color: #94A3B8;
      padding-bottom: 2mm;
      direction: ltr;
    }}

    /* داشبورد اینفوگرافیک (تاریک و مدرن مطابق code_artifact) */
    .dashboard-wrap {{
      width: 100%;
      padding-top: 2mm;
    }}

    .layout-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 8px;
      table-layout: fixed;
    }}

    .premium-card {{
      background: linear-gradient(145deg, #161F33 0%, #0F1626 100%);
      border: 1px solid rgba(255, 255, 255, 0.10);
      border-radius: 16px;
      padding: 12px 14px;
      vertical-align: top;
    }}

    .kpi-label {{
      font-size: 8.2pt;
      color: #94A3B8;
      margin-bottom: 4px;
    }}

    .kpi-value {{
      font-size: 14.5pt;
      font-weight: bold;
      margin-bottom: 8px;
      line-height: 1.25;
    }}

    .kpi-footer {{
      border-top: 1px solid #1E293B;
      padding-top: 7px;
      font-size: 7.4pt;
      color: #CBD5E1;
    }}

    .kpi-badge {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 6px;
      margin-left: 3px;
      font-weight: bold;
    }}

    .prog-track {{
      width: 100%;
      height: 8px;
      background-color: #1E293B;
      border-radius: 99px;
      overflow: hidden;
    }}

    .prog-fill {{
      height: 100%;
      border-radius: 99px;
    }}

    /* بخش میانی: توزیع زمان و نمودار ستونی */
    .sec-title {{
      font-size: 10.2pt;
      font-weight: bold;
      color: #FFFFFF;
      margin-bottom: 8px;
    }}

    .part-dist-labels {{
      width: 100%;
      font-size: 7.5pt;
      font-weight: bold;
      margin-bottom: 5px;
    }}

    .stacked-bar {{
      width: 100%;
      height: 10px;
      background-color: #1E293B;
      border-radius: 99px;
      border-collapse: collapse;
      table-layout: fixed;
      margin-bottom: 10px;
    }}

    .stacked-seg-r {{
      height: 10px;
      border-radius: 0 99px 99px 0;
    }}

    .stacked-seg-m {{
      height: 10px;
    }}

    .stacked-seg-l {{
      height: 10px;
      border-radius: 99px 0 0 99px;
    }}

    .subj-row {{
      margin-bottom: 7px;
    }}

    .subj-row-tbl {{
      width: 100%;
      border-collapse: collapse;
      font-size: 7.8pt;
      margin-bottom: 3px;
    }}

    /* نمودار میله‌ای روزانه */
    .chart-table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-top: 12px;
    }}

    .chart-col {{
      height: 145px;
      vertical-align: bottom;
      text-align: center;
      padding: 0 3px;
      border-bottom: 1px solid #1E293B;
    }}

    .bar-num {{
      font-size: 7.6pt;
      font-weight: bold;
      margin-bottom: 4px;
    }}

    .bar-pillar {{
      width: 22px;
      border-radius: 7px 7px 0 0;
      margin: 0 auto;
    }}

    .bar-day {{
      font-size: 7.2pt;
      color: #94A3B8;
      padding-top: 6px;
      text-align: center;
      font-weight: bold;
    }}

    /* کارت‌های مباحث دروس در پایین */
    .topic-card-cell {{
      vertical-align: top;
    }}

    .topic-card {{
      background: linear-gradient(145deg, #161F33 0%, #0F1626 100%);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 14px;
      padding: 9px 8px;
      min-height: 140px;
    }}

    .topic-card-hdr-tbl {{
      width: 100%;
      border-collapse: collapse;
      border-bottom: 1px solid #1E293B;
      margin-bottom: 7px;
    }}

    .topic-card-hdr-tbl td {{
      padding-bottom: 5px;
      vertical-align: middle;
    }}

    .topic-card-title {{
      font-size: 8.8pt;
      font-weight: bold;
      white-space: nowrap;
    }}

    .topic-card-badge {{
      display: inline-block;
      font-size: 6.8pt;
      font-weight: bold;
      padding: 1.5px 5px;
      border-radius: 5px;
      white-space: nowrap;
    }}

    .topic-pill {{
      background-color: rgba(15, 23, 42, 0.65);
      border: 1px solid rgba(51, 65, 85, 0.55);
      border-radius: 7px;
      padding: 4px 6px;
      margin-bottom: 4px;
      font-size: 7.2pt;
      color: #E2E8F0;
      line-height: 1.3;
    }}

    .topic-dot {{
      display: inline-block;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      margin-left: 4px;
      vertical-align: middle;
    }}
  </style>
</head>
<body>
  <!-- صفحه اول: کاور اختصاصی دکتر هاشمی -->
  <div class="cover-page">
    <img class="cover-bg" src="{cover_uri}" alt="Cover" />
    <div class="cover-badge-box">
      <div class="cover-badge-title">وضعیت هفتگی اختصاصی: {safe_student}</div>
      <div class="cover-badge-subtitle">{cover_line_2}</div>
    </div>
  </div>

  <!-- سربرگ صفحه وضعیت هفتگی -->
  <div class="running-header">
    <table class="header-banner">
      <tr>
        <td class="header-side">
          <span class="header-student-pill">{doctor_student_header}</span>
        </td>
        <td class="header-center">
          <img src="{cal_uri}" alt="Calendar" />
        </td>
        <td class="header-side">
          <span class="header-date-pill">{short_range}</span>
        </td>
      </tr>
    </table>
  </div>

  <div class="running-footer">
    The only easy day was yesterday!
  </div>

  <!-- داشبورد وضعیت هفتگی در یک صفحه A4 -->
  <div class="dashboard-wrap">
    <!-- ردیف اول: ۳ کارت KPI -->
    <table class="layout-table">
      <tr>
        <td class="premium-card" style="width: 36%;">
          <div class="kpi-label">مجموع ساعت مطالعه</div>
          <div class="kpi-value" style="color: #FFFFFF;">{total_hrs_verbose}</div>
          <div class="kpi-footer">
            <span class="kpi-badge" style="background:#1E293B; color:#E2E8F0;">میانگین: {avg_hrs_fa} ساعت</span>
            <span class="kpi-badge" style="background:rgba(14,165,233,0.15); color:#38BDF8;">آموزش: {learn_hrs_fa}س</span>
            <span class="kpi-badge" style="background:rgba(245,158,11,0.15); color:#FBBF24;">تسلط: {master_hrs_fa}س</span>
          </div>
        </td>

        <td class="premium-card" style="width: 32%;">
          <div class="kpi-label">هدف‌گذاری تعداد تست</div>
          <div class="kpi-value" style="color: #34D399;">{test_range_fa}</div>
          <div class="kpi-footer" style="padding-top: 11px;">
            <div class="prog-track">
              <div class="prog-fill" style="width: 82%; background: linear-gradient(90deg, #14B8A6, #34D399);"></div>
            </div>
          </div>
        </td>

        <td class="premium-card" style="width: 32%;">
          <div class="kpi-label">تعداد پارت‌های اجرایی</div>
          <div class="kpi-value" style="color: #C084FC;">{total_parts_fa} پارت</div>
          <div class="kpi-footer">
            <span style="color:#38BDF8; font-weight:bold;">{learn_cnt_fa} آموزش</span> •
            <span style="color:#FBBF24; font-weight:bold;">{master_cnt_fa} تسلط</span> •
            <span style="color:#34D399; font-weight:bold;">{review_cnt_fa} مرور</span>
          </div>
        </td>
      </tr>
    </table>

    <!-- ردیف دوم: توزیع زمان دروس و نمودار روند مطالعه روزانه -->
    <table class="layout-table">
      <tr>
        <td class="premium-card" style="width: 45%;">
          <div class="sec-title">توزیع زمان بر اساس نوع پارت و دروس</div>
          <div class="part-dist-labels">
            <span style="color:#38BDF8;">آموزش: {learn_hrs_fa}س ({to_persian_digits(learn_pct)}٪)</span>
            &nbsp;|&nbsp;
            <span style="color:#FBBF24;">تسلط: {master_hrs_fa}س ({to_persian_digits(master_pct)}٪)</span>
            &nbsp;|&nbsp;
            <span style="color:#34D399;">مرور: {review_hrs_fa}س ({to_persian_digits(review_pct)}٪)</span>
          </div>
          <table class="stacked-bar">
            <tr>
              <td class="stacked-seg-r" style="width: {max(5, learn_pct)}%; background:#0EA5E9;"></td>
              <td class="stacked-seg-m" style="width: {max(5, master_pct)}%; background:#F59E0B;"></td>
              <td class="stacked-seg-l" style="width: {max(4, review_pct)}%; background:#10B981;"></td>
            </tr>
          </table>
          <div style="border-top: 1px solid #1E293B; margin: 8px 0;"></div>
          {"".join(subject_progress_rows)}
        </td>

        <td class="premium-card" style="width: 55%;">
          <table style="width:100%; border-collapse:collapse; margin-bottom:6px;">
            <tr>
              <td style="text-align:right; font-size:10.2pt; font-weight:bold; color:#FFFFFF;">
                نمودار روند ساعت مطالعه روزانه
              </td>
              <td style="text-align:left;">
                <span style="font-size:8pt; font-weight:bold; background:#1E293B; color:#CBD5E1; padding:2px 8px; border-radius:8px;">
                  {total_hrs_verbose}
                </span>
              </td>
            </tr>
          </table>
          <table class="chart-table">
            <tr>
              {"".join(bar_cols_html)}
            </tr>
            <tr>
              {"".join(bar_days_html)}
            </tr>
          </table>
        </td>
      </tr>
    </table>

    <!-- ردیف سوم: کارت‌های مباحث هر درس -->
    <table class="layout-table">
      <tr>
        {"".join(topic_cards_html)}
      </tr>
    </table>
  </div>
</body>
</html>
"""
    return html_doc


def generate_study_plan_pdf(
    plan_data: dict,
    student_name: str,
    date_info: dict,
    output_path: str | Path,
    assets_dir: str | Path | None = None,
    include_summary: bool = True,
    sync_weekday_names: bool = True,
) -> Path:
    """تولید سریع فایل PDF برنامه مطالعاتی اصلی با کش حافظه."""
    if assets_dir is None:
        assets_dir = Path(__file__).resolve().parent.parent / "assets"
    else:
        assets_dir = Path(assets_dir)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html_str = build_study_plan_html(
        plan_data=plan_data,
        student_name=student_name,
        date_info=date_info,
        assets_dir=assets_dir,
        include_summary=include_summary,
        sync_weekday_names=sync_weekday_names,
    )

    weasyprint.HTML(string=html_str).write_pdf(
        str(output_file), font_config=_SHARED_FONT_CONFIG
    )
    return output_file


def generate_weekly_status_pdf(
    plan_data: dict,
    student_name: str,
    date_info: dict,
    output_path: str | Path,
    assets_dir: str | Path | None = None,
) -> Path:
    """تولید سریع فایل PDF جداگانه «وضعیت هفتگی» (اینفوگرافیک) با فونت پینار."""
    if assets_dir is None:
        assets_dir = Path(__file__).resolve().parent.parent / "assets"
    else:
        assets_dir = Path(assets_dir)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    html_str = build_weekly_status_html(
        plan_data=plan_data,
        student_name=student_name,
        date_info=date_info,
        assets_dir=assets_dir,
    )

    weasyprint.HTML(string=html_str).write_pdf(
        str(output_file), font_config=_SHARED_FONT_CONFIG
    )
    return output_file
