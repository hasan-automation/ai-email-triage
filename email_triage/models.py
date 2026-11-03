"""Data shapes: an email, Claude's structured triage of it, and the combined result."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Display order everywhere (reports, dashboard): most pressing first.
CATEGORIES = ("Urgent", "Sales Lead", "Support", "Billing", "Other", "Spam")
Category = Literal["Urgent", "Sales Lead", "Support", "Billing", "Other", "Spam"]


class Triage(BaseModel):
    """What Claude must return for each email. Enforced by structured outputs:
    the API only produces JSON matching this schema, and the SDK validates it."""

    category: Category = Field(description="Exactly one category; see the instructions.")
    sender_name: str = Field(description="The sender's name as written in the email or header. Empty string if unknown.")
    company: str = Field(
        description="The sender's company or organisation, from the signature or email domain. Empty string if not stated. Never guess."
    )
    summary: str = Field(description="One plain-English sentence: what the sender wants or what happened.")
    urgency: Literal[1, 2, 3, 4, 5] = Field(
        description="1 = can wait a week, 2 = this week, 3 = reply within a day, 4 = today, 5 = drop everything."
    )
    urgency_reason: str = Field(description="A few words explaining the urgency score.")
    confidence: Literal["high", "medium", "low"] = Field(description="How sure you are about the category.")
    needs_human: bool = Field(
        description="True if a person should look before replying: ambiguous, money disputes or refunds, legal, security, or the reply needs facts you don't have."
    )
    draft_reply: str = Field(description="Short polite reply to send, or an empty string for Spam.")


@dataclass
class Email:
    id: str
    sender: str  # raw From header, e.g. 'Maria Gonzalez <maria@bluebirdbakery.example>'
    sender_name: str
    sender_email: str
    to: str
    date: str
    subject: str
    body: str
    # Hand-written label(s) used only to measure accuracy. Never sent to Claude.
    expected_category: Optional[list[str]] = None


@dataclass
class TriageResult:
    email: Email
    triage: Triage
    error: Optional[str] = None  # set when Claude couldn't analyse the email
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def matches_expected(self) -> Optional[bool]:
        if not self.email.expected_category:
            return None
        return self.triage.category in self.email.expected_category

    def to_dict(self) -> dict:
        return {
            "email": asdict(self.email),
            "triage": self.triage.model_dump(),
            "error": self.error,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TriageResult":
        return cls(
            email=Email(**data["email"]),
            triage=Triage.model_validate(data["triage"]),
            error=data.get("error"),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


def failed_triage(email: Email, reason: str) -> Triage:
    """Placeholder used when an email couldn't be analysed: always flagged for a human."""
    return Triage(
        category="Other",
        sender_name=email.sender_name,
        company="",
        summary=f"Could not be analysed automatically ({reason}). Please read it yourself.",
        urgency=3,
        urgency_reason="not analysed",
        confidence="low",
        needs_human=True,
        draft_reply="",
    )


def sort_key(result: TriageResult):
    """Urgent category first, then emails that couldn't be analysed (they could be anything),
    then highest urgency, then category order, newest first."""
    t = result.triage
    return (t.category != "Urgent", result.error is None, -t.urgency, CATEGORIES.index(t.category),
            _neg_date(result.email.date))


def _neg_date(date: str) -> str:
    # ISO dates sort as text; invert characters so newer sorts first within a group.
    return "".join(chr(0x10FFFF - ord(c)) for c in date)


@dataclass
class RunInfo:
    """Facts about a run, shown in the reports."""
    mode: str  # "live" or "demo"
    model: str
    business_name: str
    generated_at: str
    results_from: str = ""  # when the saved demo results were produced
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Optional[float] = None
    notes: list[str] = field(default_factory=list)
