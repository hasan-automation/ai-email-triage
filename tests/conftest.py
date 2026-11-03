"""Shared test helpers: a fake Claude client so no test ever calls the real API."""
import threading
import time
from types import SimpleNamespace

import httpx2
import pytest

import anthropic
from email_triage.models import Email, Triage


def make_triage(**overrides) -> Triage:
    data = dict(
        category="Support", sender_name="Pat", company="Acme", summary="Needs help.", urgency=2,
        urgency_reason="routine", confidence="high", needs_human=False,
        draft_reply="Hi Pat,\n\nThanks - we're on it.\n\n[Your name]\nBrightside Web Studio",
    )
    data.update(overrides)
    return Triage(**data)


def make_email(id="e1", subject="Help", body="My site is broken.", **overrides) -> Email:
    data = dict(id=id, sender="Pat Lee <pat@acme.example>", sender_name="Pat Lee", sender_email="pat@acme.example",
                to="support@brightsideweb.example", date="2026-11-03T09:00:00-06:00", subject=subject, body=body)
    data.update(overrides)
    return Email(**data)


def api_error(cls, status: int):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(f"HTTP {status}", response=httpx2.Response(status, request=request), body=None)


def connection_error():
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))


class FakeClient:
    """Stands in for anthropic.Anthropic(). `behaviour(email_text)` returns a Triage,
    a response-like object, or raises - per call."""

    def __init__(self, behaviour=None, delay=None):
        self.calls = []
        self._lock = threading.Lock()
        self._behaviour = behaviour or (lambda text: make_triage())
        self._delay = delay
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
        text = kwargs["messages"][0]["content"]
        if self._delay:
            time.sleep(self._delay(text))
        outcome = self._behaviour(text)
        if isinstance(outcome, Triage):
            return SimpleNamespace(stop_reason="end_turn", parsed_output=outcome,
                                   usage=SimpleNamespace(input_tokens=100, output_tokens=50))
        return outcome


@pytest.fixture
def fake_client():
    return FakeClient()
