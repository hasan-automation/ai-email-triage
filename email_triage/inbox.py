"""Load emails from a JSON file or a folder of .eml files (as exported from Gmail/Outlook)."""
from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from .models import Email


def load_inbox(path: str | Path) -> list[Email]:
    p = Path(path)
    if p.is_dir():
        files = sorted(p.glob("*.eml"))
        if not files:
            raise FileNotFoundError(f"No .eml files found in {p}")
        return [load_eml(f) for f in files]
    if not p.exists():
        raise FileNotFoundError(f"Can't find {p}")
    if p.suffix.lower() == ".eml":
        return [load_eml(p)]
    if p.suffix.lower() == ".json":
        return load_json(p)
    raise ValueError(f"Unsupported inbox file: {p.name} (use a .json file or a folder of .eml files)")


def load_json(path: Path) -> list[Email]:
    records = json.loads(path.read_text(encoding="utf-8"))
    emails = []
    for i, rec in enumerate(records, start=1):
        name, addr = parseaddr(rec.get("from", ""))
        emails.append(Email(
            id=str(rec.get("id") or f"e{i:02d}"),
            sender=rec.get("from", ""),
            sender_name=name,
            sender_email=addr,
            to=rec.get("to", ""),
            date=rec.get("date", ""),
            subject=rec.get("subject", ""),
            body=rec.get("body", ""),
            expected_category=rec.get("expected_category"),
        ))
    return emails


def load_eml(path: Path) -> Email:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    name, addr = parseaddr(str(msg.get("From", "")))
    try:
        date = parsedate_to_datetime(str(msg["Date"])).isoformat() if msg["Date"] else ""
    except (TypeError, ValueError):
        date = str(msg.get("Date", ""))
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        body = ""
    elif part.get_content_type() == "text/html":
        body = html_to_text(part.get_content())
    else:
        body = part.get_content()
    return Email(
        id=path.stem,
        sender=str(msg.get("From", "")),
        sender_name=name,
        sender_email=addr,
        to=str(msg.get("To", "")),
        date=date,
        subject=str(msg.get("Subject", "")),
        body=body.strip(),
    )


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)
