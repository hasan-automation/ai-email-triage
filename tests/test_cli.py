import json
from pathlib import Path

import pytest

import anthropic
from email_triage import cli
from email_triage.classifier import TriageAborted

from conftest import FakeClient, make_triage

FAKE_KEY = "sk-ant-TEST-not-a-real-key-1234567890"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No test reads the real .env or writes the real demo file."""
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "DEMO_RESULTS", tmp_path / "demo" / "results.json")
    for var in ["ANTHROPIC_API_KEY", "CLAUDE_MODEL", "BUSINESS_NAME", "BUSINESS_DESCRIPTION"]:
        monkeypatch.delenv(var, raising=False)


def no_network(*args, **kwargs):
    raise AssertionError("the API client must not be created")


def test_no_key_explains_what_to_do(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(anthropic, "Anthropic", no_network)
    assert cli.main(["--out", str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "No API key found" in out and ".env" in out and "--demo" in out
    assert not (tmp_path / "out").exists()


def test_live_run_with_fake_client(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    created = {}

    def fake_anthropic(api_key, **options):
        created["key"] = api_key
        return FakeClient(lambda text: make_triage(category="Spam" if "Rank Masters" in text else "Sales Lead"))

    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic)
    out = tmp_path / "out"
    assert cli.main(["--out", str(out), "--save-demo"]) == 0
    assert created["key"] == FAKE_KEY
    printed = capsys.readouterr().out
    assert FAKE_KEY not in printed, "the key must never be printed"
    assert "Sorting 25 emails with claude-haiku-5-5" in printed
    assert "Spam: 1" in printed and "Sales Lead: 24" in printed
    for name in ["results.json", "triage_report.xlsx", "dashboard.html"]:
        assert (out / name).exists()
    saved = json.loads(cli.DEMO_RESULTS.read_text(encoding="utf-8"))
    assert len(saved["results"]) == 25 and saved["run"]["model"] == "claude-haiku-5-5"
    assert FAKE_KEY not in cli.DEMO_RESULTS.read_text(encoding="utf-8")


def test_limit_and_settings_from_env(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("BUSINESS_NAME", "Acme Plumbing")
    client = FakeClient()
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key, **options: client)
    assert cli.main(["--out", str(tmp_path), "--limit", "3"]) == 0
    assert len(client.calls) == 3
    assert client.calls[0]["model"] == "claude-sonnet-5-5"
    assert "Acme Plumbing" in client.calls[0]["system"]
    assert "Acme Plumbing - Inbox triage" in (tmp_path / "dashboard.html").read_text(encoding="utf-8")


def test_rejected_key_stops_cleanly(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key, **options: object())

    def abort(*a, **k):
        raise TriageAborted("The API key was rejected. Check ANTHROPIC_API_KEY in your .env file.")

    monkeypatch.setattr(cli, "triage_inbox", abort)
    assert cli.main(["--out", str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "Stopped: The API key was rejected" in out
    assert FAKE_KEY not in out


def test_demo_mode_needs_no_key_and_makes_no_calls(monkeypatch, tmp_path, capsys):
    # First produce a saved run (with a fake client), then use it in demo mode.
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key, **options: FakeClient())
    assert cli.main(["--out", str(tmp_path / "first"), "--save-demo"]) == 0
    capsys.readouterr()

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(anthropic, "Anthropic", no_network)
    out = tmp_path / "demo_out"
    assert cli.main(["--demo", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "Demo mode: using saved results" in printed
    assert ">Demo data</span>" in (out / "dashboard.html").read_text(encoding="utf-8")
    assert (out / "triage_report.xlsx").exists()
    assert not (out / "results.json").exists()  # demo doesn't overwrite saved results


def test_demo_without_saved_results(tmp_path, capsys):
    assert cli.main(["--demo", "--out", str(tmp_path)]) == 1
    assert "No saved demo results" in capsys.readouterr().out


def test_bad_inbox_path(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key, **options: FakeClient())
    assert cli.main(["--inbox", str(tmp_path / "nope.json"), "--out", str(tmp_path)]) == 1
    assert "Error: Can't find" in capsys.readouterr().out


ROOT = Path(__file__).resolve().parent.parent


def test_env_file_is_git_ignored_and_example_has_no_key():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignore and "!.env.example" in ignore
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=\n" in example
    assert "sk-ant-" not in example


def test_committed_demo_results_are_valid_if_present():
    real_demo = ROOT / "demo" / "results.json"
    if not real_demo.exists():
        pytest.skip("demo results are created by the first real run")
    results, info = cli.load_saved(real_demo)
    assert len(results) == 25
    assert info.model
    assert "sk-ant-" not in real_demo.read_text(encoding="utf-8")
