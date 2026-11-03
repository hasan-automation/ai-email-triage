"""A single self-contained HTML dashboard (no internet needed, opens in any browser)."""
from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .models import CATEGORIES, RunInfo, TriageResult, sort_key

URGENCY = {  # level -> (label, status role or None)
    5: ("Drop everything", "critical"),
    4: ("Reply today", "serious"),
    3: ("Within a day", "warning"),
    2: ("This week", None),
    1: ("Can wait", None),
}

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --surface-2: #f3f2ee;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #6f6d68;
  --hairline: rgba(11,11,11,0.10); --grid: #e1e0d9; --axis: #c3c2b7;
  --series: #2a78d6;
  --critical: #d03b3b; --serious: #ec835a; --warning: #fab219;
  --review-bg: #fff6dc; --review-ink: #7a4b00;
  --chip: #eceae4; --focus: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --surface-2: #222220;
    --ink: #f0efec; --ink-2: #c3c2b7; --muted: #a3a198;
    --hairline: rgba(255,255,255,0.10); --grid: #2c2c2a; --axis: #383835;
    --series: #3987e5;
    --review-bg: #3a2e12; --review-ink: #f5d48a;
    --chip: #2c2c2a; --focus: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --surface-2: #222220;
  --ink: #f0efec; --ink-2: #c3c2b7; --muted: #a3a198;
  --hairline: rgba(255,255,255,0.10); --grid: #2c2c2a; --axis: #383835;
  --series: #3987e5;
  --review-bg: #3a2e12; --review-ink: #f5d48a;
  --chip: #2c2c2a; --focus: #3987e5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 28px 20px 48px; }
header h1 { font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }
header p { margin: 0; color: var(--ink-2); }
.banner { margin: 16px 0 0; padding: 10px 14px; border-radius: 8px; background: var(--surface-2);
  border: 1px solid var(--hairline); color: var(--ink-2); font-size: 14px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 22px 0; }
.tile { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 14px 16px; }
.tile .label { font-size: 13px; color: var(--ink-2); display: flex; gap: 6px; align-items: center; }
.tile .value { font-size: 30px; font-weight: 650; margin-top: 2px; }
.panel { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 18px 20px; margin-bottom: 22px; }
.panel h2 { font-size: 16px; margin: 0 0 12px; }
.bars { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px; align-items: center; position: relative; }
.bar-label { font-size: 14px; color: var(--ink-2); padding: 3px 0; }
.bar-track { padding: 4px 44px 4px 0; cursor: default; }
.bar-area { position: relative; height: 18px; border-left: 1px solid var(--axis); }
.bar { height: 14px; margin-top: 2px; background: var(--series); border-radius: 0 4px 4px 0; }
.bar-value { position: absolute; top: 0; font-size: 13px; color: var(--ink); font-variant-numeric: tabular-nums; }
.tooltip { position: absolute; pointer-events: none; background: var(--ink); color: var(--surface);
  font-size: 13px; padding: 6px 9px; border-radius: 6px; white-space: nowrap; transform: translate(-50%, -110%); }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 14px; }
.filters button { font: inherit; font-size: 14px; border: 1px solid var(--hairline); background: var(--surface);
  color: var(--ink); padding: 6px 12px; border-radius: 999px; cursor: pointer; }
.filters button[aria-pressed="true"] { background: var(--ink); color: var(--surface); border-color: var(--ink); }
.filters button:focus-visible, summary:focus-visible, .copy:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }
.card-top { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }
.card h3 { font-size: 16px; margin: 0 0 2px; overflow-wrap: anywhere; }
.meta { font-size: 13px; color: var(--muted); margin-bottom: 8px; overflow-wrap: anywhere; }
.chip { font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: var(--chip); color: var(--ink); }
.chip.review { background: var(--review-bg); color: var(--review-ink); }
.urg { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: var(--ink); }
.urg .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--axis); }
.urg.critical .dot { background: var(--critical); } .urg.serious .dot { background: var(--serious); }
.urg.warning .dot { background: var(--warning); }
.urg .icon { font-size: 12px; }
.summary { margin: 0 0 4px; }
.why { margin: 0; font-size: 13px; color: var(--ink-2); }
details { margin-top: 10px; border-top: 1px solid var(--hairline); padding-top: 8px; }
summary { cursor: pointer; font-size: 14px; font-weight: 600; color: var(--ink-2); }
.reply, .original { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--surface-2); border-radius: 8px;
  padding: 12px 14px; margin: 8px 0 0; font-size: 14px; }
.original { font-family: ui-monospace, Consolas, monospace; font-size: 13px; color: var(--ink-2); }
.copy { font: inherit; font-size: 13px; margin-top: 8px; border: 1px solid var(--hairline); background: var(--surface);
  color: var(--ink); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.error { color: var(--review-ink); font-size: 13px; margin: 4px 0 0; }
footer { color: var(--muted); font-size: 13px; margin-top: 28px; }
table.sr { position: absolute; left: -9999px; }
@media (max-width: 520px) { .tile .value { font-size: 24px; } header h1 { font-size: 22px; } }
"""

JS = """
(function () {
  var buttons = document.querySelectorAll('.filters button');
  var cards = document.querySelectorAll('.card');
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      buttons.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      var f = b.dataset.filter;
      cards.forEach(function (c) {
        var show = f === 'all' || (f === 'review' ? c.dataset.review === '1' : c.dataset.category === f);
        c.hidden = !show;
      });
    });
  });
  document.querySelectorAll('.copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.previousElementSibling.textContent;
      var done = function () { btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = 'Copy reply'; }, 1500); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { btn.textContent = 'Select the text to copy'; });
    });
  });
  var tip = document.querySelector('.tooltip'), bars = document.querySelector('.bars');
  document.querySelectorAll('.bar-track').forEach(function (t) {
    t.addEventListener('mousemove', function (ev) {
      var box = bars.getBoundingClientRect();
      tip.textContent = t.dataset.tip; tip.hidden = false;
      tip.style.left = (ev.clientX - box.left) + 'px'; tip.style.top = (ev.clientY - box.top) + 'px';
    });
    t.addEventListener('mouseleave', function () { tip.hidden = true; });
  });
})();
"""


def _urgency_badge(level: int) -> str:
    label, role = URGENCY[level]
    icon = {"critical": "&#9650;", "serious": "&#9650;", "warning": "&#9679;"}.get(role, "")
    cls = f"urg {role}" if role else "urg"
    return (f'<span class="{cls}"><span class="dot" aria-hidden="true"></span>'
            f'Urgency {level} &middot; {label}</span>')


def _card(r: TriageResult) -> str:
    t, e = r.triage, r.email
    who = t.sender_name or e.sender_name or e.sender_email
    sender_bits = [escape(who)] + ([escape(t.company)] if t.company else []) + [escape(e.sender_email)]
    received = escape(e.date.replace("T", " ")[:16])
    chips = [f'<span class="chip">{escape(t.category)}</span>', _urgency_badge(t.urgency)]
    if t.needs_human:
        chips.append('<span class="chip review">Needs a person</span>')
    if t.confidence != "high":
        chips.append(f'<span class="chip">{escape(t.confidence.capitalize())} confidence</span>')
    if t.draft_reply.strip():
        reply = (f'<details open><summary>Draft reply</summary><div class="reply">{escape(t.draft_reply)}</div>'
                 f'<button class="copy" type="button">Copy reply</button></details>')
    else:
        reply = '<p class="why">No reply drafted' + (" (spam)." if t.category == "Spam" else ".") + "</p>"
    error = f'<p class="error">&#9888; {escape(r.error)}</p>' if r.error else ""
    original = (f'<details><summary>Original email</summary><div class="original">From: {escape(e.sender)}\n'
                f'Subject: {escape(e.subject)}\n\n{escape(e.body)}</div></details>')
    return (
        f'<article class="card" data-category="{escape(t.category)}" data-review="{1 if t.needs_human else 0}">'
        f'<div class="card-top">{"".join(chips)}</div>'
        f'<h3>{escape(e.subject) or "(no subject)"}</h3>'
        f'<div class="meta">{" &middot; ".join(sender_bits)} &middot; {received}</div>'
        f'<p class="summary">{escape(t.summary)}</p>'
        f'<p class="why">Why: {escape(t.urgency_reason)}</p>{error}{reply}{original}</article>'
    )


def render_html(results: list[TriageResult], info: RunInfo) -> str:
    ordered = sorted(results, key=sort_key)
    counts = Counter(r.triage.category for r in results)
    total = len(results)
    review = sum(r.triage.needs_human for r in results)
    today = sum(r.triage.urgency >= 4 for r in results)
    top = max(counts.values()) if counts else 1

    tiles = [
        ("Emails", total, ""),
        ("Urgent", counts.get("Urgent", 0), '<span class="urg critical"><span class="dot"></span></span>'),
        ("Reply today (4-5)", today, ""),
        ("Need a person", review, ""),
        ("Sales leads", counts.get("Sales Lead", 0), ""),
        ("Spam caught", counts.get("Spam", 0), ""),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="label">{icon}{escape(label)}</div><div class="value">{value}</div></div>'
        for label, value, icon in tiles
    )

    bars_html = []
    for cat in CATEGORIES:
        n = counts.get(cat, 0)
        pct = n / total if total else 0
        width = 100 * n / top if top else 0
        bars_html.append(
            f'<div class="bar-label">{escape(cat)}</div>'
            f'<div class="bar-track" data-tip="{escape(cat)}: {n} email{"s" if n != 1 else ""} ({pct:.0%})">'
            f'<div class="bar-area"><div class="bar" style="width:{width:.1f}%;{"min-width:3px" if n else ""}"></div>'
            f'<span class="bar-value" style="left:calc({width:.1f}% + 6px)">{n}</span></div></div>'
        )
    table_rows = "".join(f"<tr><td>{escape(c)}</td><td>{counts.get(c, 0)}</td></tr>" for c in CATEGORIES)

    filters = [("all", f"All ({total})")] + [
        (c, f"{c} ({counts.get(c, 0)})") for c in CATEGORIES if counts.get(c, 0)
    ] + [("review", f"Needs a person ({review})")]
    filters_html = "".join(
        f'<button type="button" data-filter="{escape(key)}" aria-pressed="{str(key == "all").lower()}">{escape(label)}</button>'
        for key, label in filters
    )

    banner = ""
    if info.mode == "demo":
        when = f" from {escape(info.results_from)}" if info.results_from else ""
        banner = (f'<div class="banner"><b>Demo mode:</b> showing saved results{when}. '
                  "No API key needed and no emails were sent anywhere.</div>")

    labelled = [r for r in results if r.matches_expected is not None]
    footer_bits = [f"Model: {escape(info.model)}", f"Generated {escape(info.generated_at)}"]
    if labelled:
        footer_bits.append(f"Agreement with hand labels: {sum(bool(r.matches_expected) for r in labelled)} of {len(labelled)}")
    if info.estimated_cost_usd is not None:
        footer_bits.append(f"Estimated API cost: ${info.estimated_cost_usd:.4f}")
    footer_bits.append(f"Tokens: {info.input_tokens:,} in / {info.output_tokens:,} out")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(info.business_name)} - Inbox Triage</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{escape(info.business_name)} - Inbox Triage</h1>
  <p>{total} emails sorted by AI: most urgent first, each with a summary and a draft reply to review.</p>
  {banner}
</header>
<section class="tiles" aria-label="Totals">{tiles_html}</section>
<section class="panel" aria-labelledby="by-cat">
  <h2 id="by-cat">Emails by category</h2>
  <div class="bars">{"".join(bars_html)}<div class="tooltip" hidden></div></div>
  <table class="sr"><caption>Emails by category</caption><tr><th>Category</th><th>Emails</th></tr>{table_rows}</table>
</section>
<section aria-labelledby="inbox">
  <h2 id="inbox" style="font-size:18px;margin:0 0 10px">Inbox, most urgent first</h2>
  <div class="filters" role="group" aria-label="Filter emails">{filters_html}</div>
  {"".join(_card(r) for r in ordered)}
</section>
<footer>{" &middot; ".join(footer_bits)}<br>Draft replies are suggestions written by AI. Read and edit before sending.</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""


def write_html(results: list[TriageResult], path: str | Path, info: RunInfo) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(results, info), encoding="utf-8")
    return path
