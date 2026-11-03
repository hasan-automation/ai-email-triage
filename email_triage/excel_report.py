"""Formatted Excel report: Summary, Inbox (urgent first), Original Emails."""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .models import CATEGORIES, RunInfo, TriageResult, sort_key

NAVY = "1F4E78"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=NAVY)
SECTION_FONT = Font(bold=True, size=12, color=NAVY)
NOTE_FONT = Font(italic=True, color="595959")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
WRAP_TOP = Alignment(wrap_text=True, vertical="top")
REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")

# Status colours carry urgency, always with a text label next to them.
URGENCY_STYLE = {
    5: ("5 - drop everything", "D03B3B", "FFFFFF"),
    4: ("4 - today", "EC835A", "FFFFFF"),
    3: ("3 - within a day", "FAB219", "0B0B0B"),
    2: ("2 - this week", None, None),
    1: ("1 - can wait", None, None),
}

INBOX_COLUMNS = [  # (header, width)
    ("#", 5), ("Urgency", 20), ("Category", 12), ("Needs a person?", 10), ("Received", 17),
    ("From", 22), ("Company", 24), ("Subject", 34), ("Summary", 48), ("Why this urgency", 26),
    ("Draft reply", 70), ("Confidence", 11), ("Email ID", 9),
]


def _header(ws, row, headers):
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row, col, text)
        cell.fill, cell.font, cell.border = HEADER_FILL, HEADER_FONT, BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _row_height(values_and_widths) -> float:
    lines = 1
    for value, width in values_and_widths:
        text = str(value or "")
        wrapped = sum(max(1, math.ceil(len(part) / max(width - 2, 1))) for part in text.split("\n"))
        lines = max(lines, wrapped)
    return min(15 * lines + 4, 400)


def write_excel(results: list[TriageResult], path: str | Path, info: RunInfo) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(results, key=sort_key)
    wb = Workbook()

    # ---------------------------------------------------------------- Summary
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"{info.business_name} - Inbox Triage"
    ws["A1"].font = TITLE_FONT
    mode = "Demo (saved results, no API calls)" if info.mode == "demo" else "Live run"
    ws["A2"] = f"{mode} - generated {info.generated_at} - model {info.model}"
    ws["A2"].font = NOTE_FONT

    counts = Counter(r.triage.category for r in results)
    total = len(results)
    ws["A4"] = "Emails by category"
    ws["A4"].font = SECTION_FONT
    _header(ws, 5, ["Category", "Emails", "Share"])
    row = 6
    for cat in CATEGORIES:
        ws.cell(row, 1, cat).border = BORDER
        ws.cell(row, 2, counts.get(cat, 0)).border = BORDER
        share = ws.cell(row, 3, (counts.get(cat, 0) / total) if total else 0)
        share.number_format, share.border = "0%", BORDER
        row += 1
    ws.cell(row, 1, "Total").font = Font(bold=True)
    ws.cell(row, 2, total).font = Font(bold=True)

    row += 2
    ws.cell(row, 1, "At a glance").font = SECTION_FONT
    row += 1
    _header(ws, row, ["Measure", "Value", ""])
    facts = [
        ("Urgent emails (category)", counts.get("Urgent", 0)),
        ("Urgency 4-5 (reply today)", sum(r.triage.urgency >= 4 for r in results)),
        ("Need a person to check", sum(r.triage.needs_human for r in results)),
        ("Draft replies written", sum(bool(r.triage.draft_reply.strip()) for r in results)),
        ("Could not be analysed", sum(r.error is not None for r in results)),
    ]
    labelled = [r for r in results if r.matches_expected is not None]
    if labelled:
        correct = sum(bool(r.matches_expected) for r in labelled)
        facts.append(("Agreement with hand labels", f"{correct} of {len(labelled)}"))
    if info.estimated_cost_usd is not None:
        facts.append(("Estimated API cost", f"${info.estimated_cost_usd:.4f}"))
    facts.append(("Tokens (input / output)", f"{info.input_tokens:,} / {info.output_tokens:,}"))
    for label, value in facts:
        row += 1
        ws.cell(row, 1, label).border = BORDER
        ws.cell(row, 2, value).border = BORDER
    if info.results_from:
        row += 2
        ws.cell(row, 1, f"Results were produced on {info.results_from}.").font = NOTE_FONT
    for note in info.notes:
        row += 1
        ws.cell(row, 1, note).font = NOTE_FONT
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 10

    # ---------------------------------------------------------------- Inbox
    ws = wb.create_sheet("Inbox")
    _header(ws, 1, [h for h, _ in INBOX_COLUMNS])
    for i, (_, width) in enumerate(INBOX_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = width
    ws.row_dimensions[1].height = 30
    for n, r in enumerate(ordered, start=1):
        t, e = r.triage, r.email
        label, fill, ink = URGENCY_STYLE[t.urgency]
        values = [
            n, label, t.category, "Yes" if t.needs_human else "", e.date.replace("T", " ")[:16],
            t.sender_name or e.sender_name or e.sender_email, t.company, e.subject, t.summary,
            t.urgency_reason, t.draft_reply or ("(no reply - spam)" if t.category == "Spam" else ""),
            t.confidence, e.id,
        ]
        excel_row = n + 1
        for col, value in enumerate(values, start=1):
            cell = ws.cell(excel_row, col, value)
            cell.alignment, cell.border = WRAP_TOP, BORDER
        if fill:
            cell = ws.cell(excel_row, 2)
            cell.fill = PatternFill("solid", fgColor=fill)
            cell.font = Font(bold=True, color=ink)
        if t.needs_human:
            ws.cell(excel_row, 4).fill = REVIEW_FILL
        if r.error:
            ws.cell(excel_row, 9).font = Font(italic=True, color="B45309")
        ws.row_dimensions[excel_row].height = _row_height(
            (v, INBOX_COLUMNS[i][1]) for i, v in enumerate(values) if i in (8, 10)
        )
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{ws.cell(1, len(INBOX_COLUMNS)).column_letter}{len(ordered) + 1}"

    # ---------------------------------------------------------------- Original emails
    ws = wb.create_sheet("Original Emails")
    cols = [("Email ID", 9), ("Received", 17), ("From", 40), ("To", 28), ("Subject", 40), ("Body", 100)]
    _header(ws, 1, [h for h, _ in cols])
    for i, (_, width) in enumerate(cols, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = width
    for n, r in enumerate(results, start=2):
        e = r.email
        values = [e.id, e.date.replace("T", " ")[:16], e.sender, e.to, e.subject, e.body]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(n, col, value)
            cell.alignment, cell.border = WRAP_TOP, BORDER
        ws.row_dimensions[n].height = _row_height([(e.body, 100)])
    ws.freeze_panes = "A2"

    wb.save(path)
    return path
