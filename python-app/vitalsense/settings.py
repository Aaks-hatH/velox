"""
The person's choices: the name used in the greeting, whether onboarding is done, demo mode,
which measurements are on, and whether the cloud AI may be used. No health values.

Each visitor keeps their own copy in their browser, in a signed session cookie (Flask's
`session`), so when the app is online for anyone, nobody sees or changes anyone else's choices.

Used by: app.py
"""

from dataclasses import asdict, dataclass, field
from flask import has_request_context, session

from .metrics import ALL_METRICS

KEY = "settings"   # where the choices live inside the session cookie


@dataclass
class Settings:
    onboarded: bool = False
    demo_mode: bool = True
    enabled_metrics: list[str] = field(default_factory=lambda: [m.id for m in ALL_METRICS])
    ai_consent: bool = False
    name: str = "Jayant-Chris"       # shown in the greeting on Today


def load() -> Settings:
    if not has_request_context():   # e.g. called from a script: there is no visitor
        return Settings()
    saved = session.get(KEY) or {}
    try:
        return Settings(**{k: v for k, v in saved.items() if k in Settings.__dataclass_fields__})
    except TypeError:
        return Settings()   # unreadable: start fresh rather than crash


def save(settings: Settings) -> None:
    session[KEY] = asdict(settings)
    session.permanent = True     # remembered for a while, not just until the browser closes


def delete_all() -> None:
    session.clear()
