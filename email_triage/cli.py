"""Command line: python triage.py [--demo] [--inbox PATH] [--out FOLDER] [--limit N] [--save-demo]"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .classifier import (DEFAULT_BUSINESS, DEFAULT_DESCRIPTION, DEFAULT_MODEL, TriageAborted,
                         estimate_cost, triage_inbox)
from .excel_report import write_excel
from .html_report import write_html
from .inbox import load_inbox
from .models import CATEGORIES, RunInfo, TriageResult

ROOT = Path(__file__).resolve().parent.parent
DEMO_RESULTS = ROOT / "demo" / "results.json"

NO_KEY_MESSAGE = """No API key found.

To run on real emails, create a file called .env in this folder containing:
    ANTHROPIC_API_KEY=your-key-here
(see "Connect your Claude API key" in the README).

To see it work without a key, run:  python triage.py --demo"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def save_results(path: Path, results: list[TriageResult], info: RunInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run = {"model": info.model, "business_name": info.business_name, "generated_at": info.generated_at,
           "input_tokens": info.input_tokens, "output_tokens": info.output_tokens,
           "estimated_cost_usd": info.estimated_cost_usd}
    path.write_text(json.dumps({"run": run, "results": [r.to_dict() for r in results]}, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def load_saved(path: Path) -> tuple[list[TriageResult], RunInfo]:
    data = json.loads(path.read_text(encoding="utf-8"))
    run = data["run"]
    results = [TriageResult.from_dict(d) for d in data["results"]]
    info = RunInfo(
        mode="demo", model=run["model"], business_name=run["business_name"], generated_at=_now(),
        results_from=run["generated_at"], input_tokens=run.get("input_tokens", 0),
        output_tokens=run.get("output_tokens", 0), estimated_cost_usd=run.get("estimated_cost_usd"),
    )
    return results, info


def run_live(args, business: str, description: str) -> tuple[list[TriageResult], RunInfo] | None:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print(NO_KEY_MESSAGE)
        return None
    if not key.startswith("sk-ant-"):
        print("Note: ANTHROPIC_API_KEY doesn't look like an Anthropic key (they start with 'sk-ant-'). Trying anyway.")
    model = os.getenv("CLAUDE_MODEL", "").strip() or DEFAULT_MODEL

    emails = load_inbox(args.inbox)
    if args.limit:
        emails = emails[: args.limit]
    print(f"Sorting {len(emails)} emails with {model}...")

    import anthropic  # imported here so --demo never touches the SDK
    # Small requests: fail fast on a stuck connection instead of the SDK's 10-minute default.
    client = anthropic.Anthropic(api_key=key, timeout=anthropic.Timeout(60.0, connect=10.0), max_retries=3)
    lock = threading.Lock()
    done = [0]

    def progress(r: TriageResult) -> None:
        with lock:
            done[0] += 1
            flag = "  (error: " + r.error + ")" if r.error else ""
            print(f"  [{done[0]:>2}/{len(emails)}] {r.triage.category:<10} urgency {r.triage.urgency}  "
                  f"{r.email.subject[:55]}{flag}", flush=True)

    try:
        results = triage_inbox(client, emails, model=model, business=business, description=description,
                               workers=args.workers, on_done=progress)
    except TriageAborted as exc:
        print(f"\nStopped: {exc}")
        return None

    tokens_in = sum(r.input_tokens for r in results)
    tokens_out = sum(r.output_tokens for r in results)
    info = RunInfo(mode="live", model=model, business_name=business, generated_at=_now(),
                   input_tokens=tokens_in, output_tokens=tokens_out,
                   estimated_cost_usd=estimate_cost(model, tokens_in, tokens_out))
    return results, info


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # e.g. accented subjects on older Windows consoles
    parser = argparse.ArgumentParser(description="Sort an inbox with Claude: category, urgency, summary, draft reply.")
    parser.add_argument("--demo", action="store_true", help="Use saved results (no API key, no API calls).")
    parser.add_argument("--inbox", default=str(ROOT / "sample_inbox" / "emails.json"),
                        help="A .json file of emails or a folder of .eml files.")
    parser.add_argument("--out", default=str(ROOT / "output"), help="Folder for the report and dashboard.")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N emails (for a quick test).")
    parser.add_argument("--workers", type=int, default=4, help="Emails processed at the same time (default 4).")
    parser.add_argument("--save-demo", action="store_true", help="Also save this run as the demo results.")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    business = os.getenv("BUSINESS_NAME", "").strip() or DEFAULT_BUSINESS
    description = os.getenv("BUSINESS_DESCRIPTION", "").strip() or DEFAULT_DESCRIPTION

    try:
        if args.demo:
            if not DEMO_RESULTS.exists():
                print(f"No saved demo results at {DEMO_RESULTS}.")
                return 1
            results, info = load_saved(DEMO_RESULTS)
            print(f"Demo mode: using saved results from {info.results_from} (no API calls).")
        else:
            live = run_live(args, business, description)
            if live is None:
                return 1
            results, info = live
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    out = Path(args.out)
    if info.mode == "live":
        save_results(out / "results.json", results, info)
        if args.save_demo:
            save_results(DEMO_RESULTS, results, info)
    try:
        xlsx = write_excel(results, out / "triage_report.xlsx", info)
        html = write_html(results, out / "dashboard.html", info)
    except PermissionError:
        print(f"Couldn't save to {out}. If the report is open in Excel, close it and try again.")
        return 1

    counts = Counter(r.triage.category for r in results)
    print("\n" + "  ".join(f"{c}: {counts.get(c, 0)}" for c in CATEGORIES))
    print(f"Need a person: {sum(r.triage.needs_human for r in results)}   "
          f"Could not analyse: {sum(r.error is not None for r in results)}")
    labelled = [r for r in results if r.matches_expected is not None]
    if labelled:
        print(f"Agreement with hand labels: {sum(bool(r.matches_expected) for r in labelled)} of {len(labelled)}")
    if info.estimated_cost_usd is not None:
        print(f"Tokens: {info.input_tokens:,} in / {info.output_tokens:,} out  (about ${info.estimated_cost_usd:.4f})")
    print(f"\nExcel report: {xlsx}\nDashboard:    {html}")
    return 0
