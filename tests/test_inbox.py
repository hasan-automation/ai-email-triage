import json

import pytest

from email_triage.inbox import html_to_text, load_inbox

PLAIN_EML = b"""From: Maria Gonzalez <maria@bluebirdbakery.example>
To: hello@brightsideweb.example
Subject: Website redesign
Date: Mon, 02 Nov 2026 08:14:00 -0600
Content-Type: text/plain; charset="utf-8"

Hi, we need a new website.
"""

HTML_EML = b"""From: "Shop" <news@shop.example>
To: hello@brightsideweb.example
Subject: =?utf-8?q?P=C3=A1gina_web?=
Date: Tue, 03 Nov 2026 10:00:00 +0000
MIME-Version: 1.0
Content-Type: text/html; charset="utf-8"

<html><head><style>p{color:red}</style><script>alert(1)</script></head>
<body><p>Hello <b>there</b></p><p>Line two</p></body></html>
"""


def test_sample_inbox_loads():
    emails = load_inbox("sample_inbox/emails.json")
    assert len(emails) == 25
    assert len({e.id for e in emails}) == 25
    first = emails[0]
    assert first.sender_name == "Maria Gonzalez"
    assert first.sender_email == "maria@bluebirdbakery.example"
    assert all(e.subject and e.body and e.date for e in emails)
    assert all(e.expected_category for e in emails)
    assert all(e.sender_email.endswith(".example") for e in emails), "sample data must only use fake domains"


def test_json_without_ids_or_labels(tmp_path):
    p = tmp_path / "inbox.json"
    p.write_text(json.dumps([{"from": "a@b.example", "subject": "Hi", "body": "Hello"}]), encoding="utf-8")
    [email] = load_inbox(p)
    assert email.id == "e01" and email.sender_email == "a@b.example" and email.sender_name == ""
    assert email.expected_category is None


def test_eml_folder(tmp_path):
    (tmp_path / "01_plain.eml").write_bytes(PLAIN_EML)
    (tmp_path / "02_html.eml").write_bytes(HTML_EML)
    (tmp_path / "notes.txt").write_text("ignored")
    plain, html = load_inbox(tmp_path)
    assert plain.id == "01_plain"
    assert plain.sender_name == "Maria Gonzalez" and plain.subject == "Website redesign"
    assert plain.body == "Hi, we need a new website."
    assert plain.date == "2026-11-02T08:14:00-06:00"
    assert html.subject == "Página web"
    assert html.body == "Hello there\nLine two"
    assert "alert" not in html.body and "color" not in html.body


def test_single_eml_file(tmp_path):
    p = tmp_path / "one.eml"
    p.write_bytes(PLAIN_EML)
    assert load_inbox(p)[0].subject == "Website redesign"


def test_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_inbox(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError, match="No .eml files"):
        load_inbox(tmp_path)
    bad = tmp_path / "inbox.csv"
    bad.write_text("x")
    with pytest.raises(ValueError, match="Unsupported"):
        load_inbox(bad)


def test_html_to_text():
    assert html_to_text("<div>A<br>B</div><ul><li>C</li></ul>") == "A\nB\nC"
