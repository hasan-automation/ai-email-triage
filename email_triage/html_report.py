"""The triage dashboard: one self-contained HTML file, laid out like an inbox tool.

Left: views and categories with counts. Middle: one dense row per email, most
urgent first. Right: the selected email's details, draft reply and original text.
Everything taken from an email is HTML-escaped here in Python; the small script
at the bottom only shows/hides elements. No external files, fonts or requests.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from .models import CATEGORIES, RunInfo, TriageResult, sort_key

URGENCY_LABELS = {5: "Drop everything", 4: "Reply today", 3: "Within a day", 2: "This week", 1: "Can wait"}

CSS = """
:root {
  color-scheme: light;
  --bg: #ffffff; --bg-side: #f7f7f5; --bg-hover: #f3f3f0; --bg-selected: #e9f0ee;
  --border: #e3e3df; --border-strong: #d2d2cc;
  --text: #1c1c1a; --text-2: #55554f; --text-3: #75756f;
  --accent: #2d6a5f; --accent-text: #ffffff;
  --pill: #efefeb; --pill-text: #45453f;
  --review: #f6eedb; --review-text: #6f5310;
  --u5: #c2413b; --u4: #d07438; --u3: #d6c48f; --u-low: #d2d2cc;
  --code: #fafaf8;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --bg: #171716; --bg-side: #1c1c1b; --bg-hover: #222220; --bg-selected: #1f2f2b;
    --border: #2c2c2a; --border-strong: #3a3a37;
    --text: #ebeae6; --text-2: #aeada7; --text-3: #8b8a84;
    --accent: #6fb0a2; --accent-text: #0f1f1b;
    --pill: #262624; --pill-text: #c9c8c2;
    --review: #352d1b; --review-text: #e2c27c;
    --u5: #e0605a; --u4: #e08a55; --u3: #7d6d42; --u-low: #3a3a37;
    --code: #1b1b1a;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #171716; --bg-side: #1c1c1b; --bg-hover: #222220; --bg-selected: #1f2f2b;
  --border: #2c2c2a; --border-strong: #3a3a37;
  --text: #ebeae6; --text-2: #aeada7; --text-3: #8b8a84;
  --accent: #6fb0a2; --accent-text: #0f1f1b;
  --pill: #262624; --pill-text: #c9c8c2;
  --review: #352d1b; --review-text: #e2c27c;
  --u5: #e0605a; --u4: #e08a55; --u3: #7d6d42; --u-low: #3a3a37;
  --code: #1b1b1a;
}
* { box-sizing: border-box; }
/* Filtering hides rows with the `hidden` attribute; without this, `.row { display: grid }` would win and keep them visible. */
[hidden] { display: none !important; }
html, body { height: 100%; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 13px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
button { font: inherit; color: inherit; }
.num { font-variant-numeric: tabular-nums; }

.app { display: grid; grid-template-rows: 44px minmax(0, 1fr); grid-template-columns: minmax(0, 1fr); height: 100vh; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 0 16px; border-bottom: 1px solid var(--border); min-width: 0; }
.topbar .name { font-weight: 600; font-size: 14px; white-space: nowrap; }
.topbar .sep { color: var(--text-3); }
.topbar .muted { color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.topbar .demo { margin-left: auto; font-size: 12px; color: var(--text-2); border: 1px solid var(--border-strong);
  border-radius: 4px; padding: 1px 6px; white-space: nowrap; }

.panes { display: grid; grid-template-columns: 200px minmax(0, 1fr) 440px; min-height: 0; }
.side { background: var(--bg-side); border-right: 1px solid var(--border); overflow-y: auto; padding: 10px 8px;
  display: flex; flex-direction: column; }
.side h2 { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-3);
  margin: 12px 8px 4px; }
.side h2:first-child { margin-top: 2px; }
.nav { display: flex; width: 100%; align-items: center; gap: 8px; border: 0; background: none; cursor: pointer;
  padding: 5px 8px; border-radius: 4px; text-align: left; color: var(--text-2); }
.nav:hover { background: var(--bg-hover); color: var(--text); }
.nav[aria-current="true"] { background: var(--bg-selected); color: var(--text); font-weight: 600; }
.nav .count { margin-left: auto; color: var(--text-3); font-weight: 400; }
.nav .mark { width: 3px; height: 12px; border-radius: 1px; background: transparent; flex: none; }
.nav[aria-current="true"] .mark { background: var(--accent); }
.run { margin-top: auto; padding: 12px 8px 4px; font-size: 12px; color: var(--text-3); border-top: 1px solid var(--border); }
.run div { display: flex; justify-content: space-between; gap: 8px; }
.run span:last-child { color: var(--text-2); text-align: right; }

.list { overflow-y: auto; min-width: 0; border-right: 1px solid var(--border); }
.list-head { position: sticky; top: 0; z-index: 1; background: var(--bg); display: flex; align-items: baseline; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); }
.list-head h1 { font-size: 14px; margin: 0; font-weight: 600; }
.list-head .hint { color: var(--text-3); font-size: 12px; margin-left: auto; }
.row { display: grid; grid-template-columns: 3px 14px 140px minmax(0, 1fr) auto 46px; align-items: center; gap: 10px;
  width: 100%; height: 38px; padding: 0 14px 0 0; border: 0; border-bottom: 1px solid var(--border); background: var(--bg);
  text-align: left; cursor: pointer; }
.row:hover { background: var(--bg-hover); }
.row[aria-selected="true"] { background: var(--bg-selected); }
.row:focus-visible, .nav:focus-visible, .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.bar { width: 3px; height: 100%; background: transparent; }
.u5 { background: var(--u5); } .u4 { background: var(--u4); } .u3 { background: var(--u3); }
.unum { color: var(--text-3); font-size: 12px; text-align: center; }
.who { min-width: 0; display: flex; flex-direction: column; line-height: 1.2; }
.who b, .who small, .line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.who b { font-weight: 600; }
.who small { color: var(--text-3); font-size: 11.5px; }
.line { min-width: 0; color: var(--text-2); }
.line .subj { color: var(--text); font-weight: 500; }
.tags { display: flex; gap: 4px; }
.tag { font-size: 11.5px; padding: 0 6px; line-height: 18px; border-radius: 4px; background: var(--pill); color: var(--pill-text);
  white-space: nowrap; }
.tag.review { background: var(--review); color: var(--review-text); }
.time { color: var(--text-3); font-size: 12px; text-align: right; }
.row.spam .who b, .row.spam .line, .row.spam .line .subj { color: var(--text-3); font-weight: 400; }
.empty { padding: 28px 14px; color: var(--text-3); }

.detail-pane { overflow-y: auto; min-width: 0; }
.detail { padding: 16px 20px 28px; }
.detail .back { display: none; }
.detail h2 { font-size: 16px; line-height: 1.35; margin: 0 0 8px; font-weight: 600; overflow-wrap: anywhere; }
.detail .tags { flex-wrap: wrap; margin-bottom: 14px; }
.meta { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 4px 12px; margin: 0 0 16px; font-size: 13px; }
.meta dt { color: var(--text-3); }
.meta dd { margin: 0; overflow-wrap: anywhere; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; background: var(--u-low); }
.dot.u5 { background: var(--u5); } .dot.u4 { background: var(--u4); } .dot.u3 { background: var(--u3); }
.section { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 14px; }
.section h3 { font-size: 12px; font-weight: 600; color: var(--text-2); margin: 0 0 6px; }
.section p { margin: 0; font-size: 14px; }
.section .note { font-size: 12px; color: var(--text-3); margin: -2px 0 6px; }
.warn { color: var(--review-text); background: var(--review); border-radius: 4px; padding: 6px 8px; margin: 0 0 12px; font-size: 13px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; font: 13.5px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--code); border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; }
pre.original { font: 12.5px/1.5 ui-monospace, "Cascadia Mono", Consolas, monospace; color: var(--text-2); }
.actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.btn { border: 1px solid var(--border-strong); background: var(--bg); border-radius: 4px; padding: 3px 10px; cursor: pointer; }
.btn:hover { background: var(--bg-hover); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); }
.actions .status { color: var(--text-3); font-size: 12px; }
.placeholder { padding: 28px 20px; color: var(--text-3); }

@media (max-width: 1100px) {
  .panes { grid-template-columns: 180px minmax(0, 1fr) 380px; }
  .row { grid-template-columns: 3px 14px 120px minmax(0, 1fr) 46px; }
  .row .tags { display: none; }
}
@media (max-width: 820px) {
  .app { height: auto; min-height: 100vh; }
  .panes { grid-template-columns: minmax(0, 1fr); }
  .side { flex-direction: row; flex-wrap: nowrap; overflow-x: auto; padding: 6px 8px; border-right: 0; border-bottom: 1px solid var(--border); }
  .side h2, .run { display: none; }
  .nav { width: auto; white-space: nowrap; }
  .list { border-right: 0; }
  .row { grid-template-columns: 3px 14px minmax(0, 1fr) 46px; height: auto; padding: 6px 12px 6px 0; }
  .row .bar { grid-column: 1; grid-row: 1 / 3; } .row .unum { grid-column: 2; grid-row: 1 / 3; }
  .row .who { grid-column: 3; grid-row: 1; } .row .time { grid-column: 4; grid-row: 1; }
  .row .line { grid-column: 3 / 5; grid-row: 2; }
  .detail-pane { display: none; }
  .app.show-detail .list, .app.show-detail .side { display: none; }
  .app.show-detail .detail-pane { display: block; }
  .detail .back { display: inline-block; margin-bottom: 10px; }
  .topbar .muted, .topbar .sep { display: none; }
  .topbar .muted.summary-line { display: inline; }
  .topbar .name { overflow: hidden; text-overflow: ellipsis; }
}
"""

JS = """
(function () {
  var app = document.querySelector('.app');
  var rows = Array.prototype.slice.call(document.querySelectorAll('.row'));
  var details = {};
  document.querySelectorAll('.detail').forEach(function (d) { details[d.dataset.for] = d; });
  var placeholder = document.querySelector('.placeholder');
  var empty = document.querySelector('.empty');
  var title = document.querySelector('.list-head h1');
  var shown = document.querySelector('.list-head .shown');

  function visible() { return rows.filter(function (r) { return !r.hidden; }); }

  function select(row, focus) {
    rows.forEach(function (r) { r.setAttribute('aria-selected', String(r === row)); r.tabIndex = r === row ? 0 : -1; });
    Object.keys(details).forEach(function (k) { details[k].hidden = !row || k !== row.dataset.id; });
    placeholder.hidden = !!row;
    if (row && focus) { row.focus(); }
  }

  rows.forEach(function (r) {
    r.addEventListener('click', function () { select(r, false); app.classList.add('show-detail'); });
  });

  document.querySelector('.list').addEventListener('keydown', function (ev) {
    var keys = { ArrowDown: 1, j: 1, ArrowUp: -1, k: -1 };
    if (!(ev.key in keys)) return;
    var vis = visible(), i = vis.indexOf(document.activeElement);
    var next = vis[Math.min(vis.length - 1, Math.max(0, (i < 0 ? 0 : i + keys[ev.key])))];
    if (next) { ev.preventDefault(); select(next, true); }
  });

  document.querySelectorAll('.nav').forEach(function (n) {
    n.addEventListener('click', function () {
      document.querySelectorAll('.nav').forEach(function (x) { x.setAttribute('aria-current', String(x === n)); });
      var f = n.dataset.filter;
      rows.forEach(function (r) {
        r.hidden = !(f === 'all' || (f === 'review' ? r.dataset.review === '1' : r.dataset.category === f));
      });
      var vis = visible();
      title.textContent = n.dataset.title;
      shown.textContent = vis.length;
      empty.hidden = vis.length > 0;
      var current = rows.filter(function (r) { return r.getAttribute('aria-selected') === 'true'; })[0];
      if (!current || current.hidden) { select(vis[0] || null, false); }
      app.classList.remove('show-detail');
      try { history.replaceState(null, '', f === 'all' ? location.pathname : '#view=' + encodeURIComponent(f)); } catch (e) {}
    });
  });

  document.querySelectorAll('.back').forEach(function (b) {
    b.addEventListener('click', function () { app.classList.remove('show-detail'); });
  });

  document.querySelectorAll('.copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = btn.closest('.section').querySelector('pre').textContent;
      var status = btn.parentNode.querySelector('.status');
      function say(msg) { status.textContent = msg; setTimeout(function () { status.textContent = ''; }, 1800); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { say('Copied'); }, function () { say('Select the text and copy it'); });
      } else { say('Select the text and copy it'); }
    });
  });

  select(rows[0] || null, false);

  // Open a view from the address bar, e.g. dashboard.html#view=Urgent (also survives a reload).
  var m = /^#view=(.+)$/.exec(location.hash);
  if (m) {
    var wanted = decodeURIComponent(m[1]);
    document.querySelectorAll('.nav').forEach(function (n) { if (n.dataset.filter === wanted) { n.click(); } });
  }
})();
"""


def _short_time(iso: str, newest_day: str) -> str:
    """'10:55' for emails on the newest day in the inbox, 'Nov 2' for older ones."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return escape(iso[:10])
    if iso[:10] == newest_day:
        return dt.strftime("%H:%M")
    return f"{dt.strftime('%b')} {dt.day}"


def _long_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return escape(iso)
    return f"{dt.strftime('%a')}, {dt.strftime('%b')} {dt.day}, {dt.year}, {dt.strftime('%H:%M')}"


def _tags(r: TriageResult, in_row: bool) -> str:
    t = r.triage
    tags = []
    if t.needs_human:
        tags.append('<span class="tag review">Review</span>')
    tags.append(f'<span class="tag">{escape(t.category)}</span>')
    if not in_row and t.confidence != "high":
        tags.append(f'<span class="tag">{escape(t.confidence.capitalize())} confidence</span>')
    return f'<span class="tags">{"".join(tags)}</span>'


def _row(r: TriageResult, newest_day: str) -> str:
    t, e = r.triage, r.email
    who = t.sender_name or e.sender_name or e.sender_email
    snippet = t.summary if not r.error else f"Not analysed: {r.error}"
    bar = f"u{t.urgency}" if t.urgency >= 3 else ""
    label = f"{who}, {e.subject}, urgency {t.urgency}, {t.category}" + (", needs review" if t.needs_human else "")
    return (
        f'<button type="button" class="row{" spam" if t.category == "Spam" else ""}" role="option" '
        f'aria-selected="false" tabindex="-1" data-id="{escape(e.id)}" data-category="{escape(t.category)}" '
        f'data-review="{1 if t.needs_human else 0}" aria-label="{escape(label)}">'
        f'<span class="bar {bar}" title="Urgency {t.urgency}: {URGENCY_LABELS[t.urgency]}"></span>'
        f'<span class="unum num">{t.urgency}</span>'
        f'<span class="who"><b>{escape(who)}</b><small>{escape(t.company) or "&nbsp;"}</small></span>'
        f'<span class="line"><span class="subj">{escape(e.subject) or "(no subject)"}</span> &ndash; {escape(snippet)}</span>'
        f'{_tags(r, in_row=True)}'
        f'<span class="time num">{_short_time(e.date, newest_day)}</span>'
        f"</button>"
    )


def _detail(r: TriageResult) -> str:
    t, e = r.triage, r.email
    who = t.sender_name or e.sender_name
    sender = f"{escape(who)} &lt;{escape(e.sender_email)}&gt;" if who else escape(e.sender_email or e.sender)
    dot = f'<span class="dot u{t.urgency}"></span>' if t.urgency >= 3 else '<span class="dot"></span>'
    warn = f'<p class="warn">Not analysed automatically: {escape(r.error)}. Read the original below.</p>' if r.error else ""
    if t.draft_reply.strip():
        reply = (
            '<div class="section"><h3>Draft reply</h3><p class="note">Written by AI. Read and edit before sending.</p>'
            f'<pre class="reply">{escape(t.draft_reply)}</pre>'
            '<div class="actions"><button type="button" class="btn primary copy">Copy reply</button>'
            '<span class="status" aria-live="polite"></span></div></div>'
        )
    else:
        why = "Spam: no reply drafted." if t.category == "Spam" else "No reply drafted."
        reply = f'<div class="section"><h3>Draft reply</h3><p class="note">{why}</p></div>'
    return (
        f'<section class="detail" data-for="{escape(e.id)}" hidden aria-label="Email details">'
        '<button type="button" class="btn back">Back to list</button>'
        f'<h2>{escape(e.subject) or "(no subject)"}</h2>{_tags(r, in_row=False)}{warn}'
        '<dl class="meta">'
        f'<dt>From</dt><dd>{sender}</dd>'
        f'<dt>Company</dt><dd>{escape(t.company) or "&ndash;"}</dd>'
        f'<dt>To</dt><dd>{escape(e.to) or "&ndash;"}</dd>'
        f'<dt>Received</dt><dd class="num">{_long_time(e.date)}</dd>'
        f'<dt>Urgency</dt><dd>{dot}<span class="num">{t.urgency}</span> &middot; {URGENCY_LABELS[t.urgency]}'
        f' &ndash; {escape(t.urgency_reason)}</dd>'
        f'<dt>Confidence</dt><dd>{escape(t.confidence.capitalize())}</dd>'
        "</dl>"
        f'<div class="section"><h3>Summary</h3><p>{escape(t.summary)}</p></div>'
        f"{reply}"
        f'<div class="section"><h3>Original email</h3><pre class="original">{escape(e.body)}</pre></div>'
        "</section>"
    )


def _header_date(info: RunInfo) -> str:
    try:
        dt = datetime.strptime(info.generated_at, "%Y-%m-%d %H:%M")
        return f"{dt.strftime('%a')}, {dt.strftime('%b')} {dt.day}, {dt.year}"
    except ValueError:
        return escape(info.generated_at)


def render_html(results: list[TriageResult], info: RunInfo) -> str:
    ordered = sorted(results, key=sort_key)
    counts = Counter(r.triage.category for r in results)
    total = len(results)
    review = sum(r.triage.needs_human for r in results)
    newest_day = max((r.email.date[:10] for r in results if r.email.date), default="")

    nav = [
        '<h2>Views</h2>',
        _nav("all", "All emails", total, current=True),
        _nav("review", "Needs review", review),
        '<h2>Categories</h2>',
    ] + [_nav(c, c, counts.get(c, 0)) for c in CATEGORIES]

    run_rows = [("Model", escape(info.model))]
    labelled = [r for r in results if r.matches_expected is not None]
    if labelled:
        run_rows.append(("Hand labels", f"{sum(bool(r.matches_expected) for r in labelled)} of {len(labelled)} match"))
    if info.estimated_cost_usd is not None:
        run_rows.append(("API cost", f"${info.estimated_cost_usd:.4f}"))
    run_rows.append(("Results from", escape(info.results_from or info.generated_at)))
    run_html = "".join(f'<div><span>{k}</span><span class="num">{v}</span></div>' for k, v in run_rows)

    summary_line = (f'<span class="num">{total}</span> emails &middot; <span class="num">{counts.get("Urgent", 0)}</span> urgent'
                    f' &middot; <span class="num">{review}</span> need review')
    demo = ('<span class="demo" title="Saved results from an earlier run. No API calls were made.">Demo data</span>'
            if info.mode == "demo" else "")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(info.business_name)} - Inbox triage</title>
<style>{CSS}</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <span class="name">{escape(info.business_name)}</span><span class="sep">/</span>
    <span class="muted">Inbox triage &middot; {_header_date(info)}</span><span class="sep">&middot;</span>
    <span class="muted summary-line">{summary_line}</span>
    {demo}
  </header>
  <div class="panes">
    <nav class="side" aria-label="Filter emails">{"".join(nav)}<div class="run">{run_html}</div></nav>
    <main class="list" aria-label="Emails">
      <div class="list-head"><h1>All emails</h1><span class="shown num">{total}</span>
        <span class="hint">Most urgent first &middot; &uarr;&darr; to move</span></div>
      <div role="listbox" aria-label="Emails, most urgent first">{"".join(_row(r, newest_day) for r in ordered)}</div>
      <p class="empty" hidden>No emails in this view.</p>
    </main>
    <aside class="detail-pane" aria-label="Selected email">
      <p class="placeholder">Select an email to see the details and draft reply.</p>
      {"".join(_detail(r) for r in ordered)}
    </aside>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
"""


def _nav(key: str, label: str, count: int, current: bool = False) -> str:
    return (f'<button type="button" class="nav" data-filter="{escape(key)}" data-title="{escape(label)}" '
            f'aria-current="{str(current).lower()}"><span class="mark"></span>{escape(label)}'
            f'<span class="count num">{count}</span></button>')


def write_html(results: list[TriageResult], path: str | Path, info: RunInfo) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(results, info), encoding="utf-8")
    return path
