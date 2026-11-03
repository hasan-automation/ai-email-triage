"""Runs the dashboard in a real headless browser (Edge or Chrome) and checks what is
actually visible after filtering. A text-only test can't catch CSS bugs like a rule
that keeps "hidden" rows on screen. Skipped when no browser is installed."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from email_triage.html_report import write_html
from email_triage.models import RunInfo, TriageResult

from conftest import make_email, make_triage

CANDIDATES = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    shutil.which("google-chrome") or "", shutil.which("chromium") or "", shutil.which("msedge") or "",
]
BROWSER = next((p for p in CANDIDATES if p and Path(p).exists()), None)
pytestmark = pytest.mark.skipif(BROWSER is None, reason="needs Edge or Chrome")

# Loads the dashboard in an iframe, then writes what's on screen into the page we dump.
PROBE = """<!doctype html><body><iframe id="f" src="{src}" style="width:1400px;height:900px"></iframe>
<script>
document.getElementById('f').onload = function () {{
  var d = this.contentDocument;
  var shown = Array.prototype.filter.call(d.querySelectorAll('.row'), function (r) {{ return r.offsetParent !== null; }});
  var detail = Array.prototype.filter.call(d.querySelectorAll('.detail'), function (s) {{ return s.offsetParent !== null; }});
  document.body.setAttribute('data-visible', shown.map(function (r) {{ return r.dataset.id; }}).join(','));
  document.body.setAttribute('data-title', d.querySelector('.list-head h1').textContent);
  document.body.setAttribute('data-detail', detail.map(function (s) {{ return s.dataset.for; }}).join(','));
  document.body.setAttribute('data-empty', String(d.querySelector('.empty').offsetParent !== null));
}};
</script></body>"""


def results():
    def r(id, category, urgency, review=False):
        return TriageResult(make_email(id, subject=f"Subject {id}"),
                            make_triage(category=category, urgency=urgency, needs_human=review))
    return [r("u1", "Urgent", 5, True), r("u2", "Urgent", 4), r("s1", "Sales Lead", 3),
            r("b1", "Billing", 3, True), r("x1", "Spam", 1)]


INFO = RunInfo(mode="live", model="m", business_name="Test Co", generated_at="2026-11-03 12:00")


def visible_after(view: str | None):
    with tempfile.TemporaryDirectory() as tmp:
        dash = write_html(results(), Path(tmp) / "dashboard.html", INFO)
        src = dash.as_uri() + (f"#view={view}" if view else "")
        probe = Path(tmp) / "probe.html"
        probe.write_text(PROBE.format(src=src), encoding="utf-8")
        out = subprocess.run(
            [BROWSER, "--headless=new", "--disable-gpu", "--no-first-run", "--allow-file-access-from-files",
             f"--user-data-dir={Path(tmp) / 'profile'}", "--dump-dom", probe.as_uri()],
            capture_output=True, text=True, timeout=60,
        ).stdout
    attrs = dict(re.findall(r'data-(visible|title|detail|empty)="([^"]*)"', out))
    assert attrs, f"probe didn't run; browser output was: {out[:300]}"
    return attrs


def test_all_emails_visible_by_default():
    a = visible_after(None)
    assert a["visible"] == "u1,u2,s1,b1,x1"
    assert a["title"] == "All emails" and a["detail"] == "u1"


@pytest.mark.parametrize("view,expected,title", [
    ("Urgent", "u1,u2", "Urgent"),
    ("Spam", "x1", "Spam"),
    ("review", "u1,b1", "Needs review"),
    ("Sales%20Lead", "s1", "Sales Lead"),
])
def test_filter_shows_only_matching_emails(view, expected, title):
    a = visible_after(view)
    assert a["visible"] == expected, "rows outside the filter must not be on screen"
    assert a["title"] == title
    assert a["detail"] == expected.split(",")[0], "detail panel follows the first visible email"
    assert a["empty"] == "false"


def test_empty_category_shows_message():
    a = visible_after("Support")
    assert a["visible"] == "" and a["empty"] == "true" and a["detail"] == ""
