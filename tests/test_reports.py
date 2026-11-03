import re

from openpyxl import load_workbook

from email_triage.excel_report import write_excel
from email_triage.html_report import render_html, write_html
from email_triage.models import RunInfo, TriageResult, failed_triage, sort_key

from conftest import make_email, make_triage


def sample_results():
    return [
        TriageResult(make_email("lead", subject="Quote please", date="2026-11-02T08:00:00-06:00",
                                expected_category=["Sales Lead"]),
                     make_triage(category="Sales Lead", urgency=3)),
        TriageResult(make_email("spam", subject="Cheap backlinks", expected_category=["Spam"]),
                     make_triage(category="Spam", urgency=1, draft_reply="")),
        TriageResult(make_email("down", subject="Site down!", expected_category=["Urgent"]),
                     make_triage(category="Urgent", urgency=5, needs_human=True)),
        TriageResult(make_email("bill", subject="Double charge", expected_category=["Support"]),  # deliberate miss
                     make_triage(category="Billing", urgency=4, needs_human=True, confidence="medium")),
        TriageResult(make_email("broken", subject="??"), failed_triage(make_email("broken"), "network error"),
                     error="network error"),
    ]


INFO = RunInfo(mode="live", model="claude-haiku-5-5", business_name="Brightside Web Studio",
               generated_at="2026-11-03 12:00", input_tokens=12_345, output_tokens=6_789, estimated_cost_usd=0.0046)


def test_sort_order_urgent_first():
    ordered = [r.email.id for r in sorted(sample_results(), key=sort_key)]
    assert ordered == ["down", "broken", "bill", "lead", "spam"]


def test_excel_report(tmp_path):
    path = write_excel(sample_results(), tmp_path / "out" / "report.xlsx", INFO)
    wb = load_workbook(path)
    assert wb.sheetnames == ["Summary", "Inbox", "Original Emails"]

    summary = {row[0]: row[1] for row in wb["Summary"].iter_rows(values_only=True) if row[0]}
    assert summary["Urgent"] == 1 and summary["Spam"] == 1 and summary["Other"] == 1 and summary["Total"] == 5
    assert summary["Need a person to check"] == 3
    assert summary["Could not be analysed"] == 1
    assert summary["Agreement with hand labels"] == "3 of 4"
    assert summary["Estimated API cost"] == "$0.0046"

    inbox = wb["Inbox"]
    assert inbox["B1"].value == "Urgency" and inbox["K1"].value == "Draft reply"
    assert [inbox.cell(r, 13).value for r in range(2, 7)] == ["down", "broken", "bill", "lead", "spam"]
    assert inbox["B2"].value == "5 - drop everything"
    assert inbox["B2"].fill.fgColor.rgb.endswith("D03B3B")
    assert inbox["D2"].value == "Yes" and inbox["I3"].value.startswith("Could not be analysed")
    assert inbox["K6"].value == "(no reply - spam)"
    assert inbox.freeze_panes == "C2" and inbox.auto_filter.ref == "A1:M6"
    assert wb["Original Emails"].max_row == 6


def test_html_dashboard_content(tmp_path):
    path = write_html(sample_results(), tmp_path / "dash.html", INFO)
    html = path.read_text(encoding="utf-8")
    assert "<title>Brightside Web Studio - Inbox triage</title>" in html
    # Rows in the list and detail panels, both most urgent first
    assert re.findall(r'class="row[^"]*"[^>]*data-id="([^"]+)"', html) == ["down", "broken", "bill", "lead", "spam"]
    assert re.findall(r'class="detail" data-for="([^"]+)"', html) == ["down", "broken", "bill", "lead", "spam"]
    # Header summary line and sidebar counts
    assert '<span class="num">5</span> emails &middot; <span class="num">1</span> urgent' in html
    assert '<span class="num">3</span> need review' in html
    assert re.search(r'data-filter="review"[^>]*>.*?Needs review<span class="count num">3</span>', html)
    assert re.search(r'data-filter="Urgent"[^>]*>.*?Urgent<span class="count num">1</span>', html)
    # Urgency: thin bar + number in the row, words in the detail panel
    assert '<span class="bar u5" title="Urgency 5: Drop everything"></span><span class="unum num">5</span>' in html
    assert '<span class="num">5</span> &middot; Drop everything' in html
    assert 'class="row spam"' in html
    assert "Spam: no reply drafted." in html
    assert "Not analysed automatically: network error." in html
    assert html.count('class="btn primary copy"') == 3  # every non-spam, analysed email has a draft
    assert "3 of 4 match" in html and "$0.0046" in html
    assert "Demo data" not in html


def test_design_rules():
    """The look-and-feel constraints for this dashboard, so they don't drift."""
    html = render_html(sample_results(), INFO)
    css = html.split("<style>")[1].split("</style>")[0]
    assert "gradient" not in css and "box-shadow" not in css and "backdrop-filter" not in css
    radii = [int(px) for px in re.findall(r"border-radius:\s*(\d+)px", css)]
    assert radii and max(r for r in radii if r != 50) <= 6  # 50% is only the urgency dot
    assert "font-variant-numeric: tabular-nums" in css
    assert "system-ui" in css
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", html), "no emoji or pictographs"

def test_html_escapes_everything_from_the_email():
    evil = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    results = [TriageResult(make_email("x", subject=evil, body=evil, sender=f"{evil} <a@b.example>"),
                            make_triage(summary=evil, draft_reply=evil, company=evil, sender_name=evil))]
    html = render_html(results, INFO)
    assert "<img" not in html
    assert html.count("<script>") == 1  # only the dashboard's own script
    assert "&lt;script&gt;" in html


def test_html_is_self_contained():
    html = render_html(sample_results(), INFO)
    assert not re.search(r'<(script|link|img|iframe)[^>]+(src|href)=', html)
    assert "@import" not in html and "url(" not in html


def test_demo_banner():
    info = RunInfo(mode="demo", model="claude-haiku-5-5", business_name="B", generated_at="now",
                   results_from="2026-11-03 15:00")
    html = render_html(sample_results(), info)
    assert ">Demo data</span>" in html and "2026-11-03 15:00" in html


def test_round_trip_to_saved_json():
    for r in sample_results():
        again = TriageResult.from_dict(r.to_dict())
        assert again.to_dict() == r.to_dict()
