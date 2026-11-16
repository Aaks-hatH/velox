"""
The person's "About you" details from onboarding: height, weight, sex at birth, date of birth
and how active they are. The AI assistant uses these as context when it compares their
Apple Health data (for example, a step count means more next to an activity level).

Privacy:
  - Kept in the visitor's own browser, in the signed session cookie, so each visitor has their own.
  - Never logged and never shown in error messages.
  - Sent to the cloud AI only when "Use cloud AI" is switched on in Settings, and then only
    as age (not the date of birth), sex at birth, height, weight and activity level.

Used by: app.py (onboarding and Settings) and assistant_ai.py (the summary sent to the AI).
"""

from dataclasses import asdict, dataclass
from datetime import date

from flask import has_request_context, session

KEY = "profile"   # where the profile lives inside the session cookie

SEXES = {"female": "Female", "male": "Male", "intersex": "Intersex", "unsaid": "Prefer not to say"}
ACTIVITY = {
    "sitting": "Mostly sitting",
    "light": "Lightly active",
    "active": "Active most days",
    "very": "Very active or training",
}

# Sensible limits, only to catch typing mistakes (not medical ranges).
HEIGHT_CM = (50, 250)
WEIGHT_KG = (20, 350)


@dataclass
class Profile:
    height_cm: float | None = None
    weight_kg: float | None = None
    sex: str = ""             # a key of SEXES
    birth_date: str = ""      # YYYY-MM-DD
    activity: str = ""        # a key of ACTIVITY

    @property
    def age(self) -> int | None:
        try:
            born = date.fromisoformat(self.birth_date)
        except ValueError:
            return None
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    @property
    def complete(self) -> bool:
        return bool(self.height_cm and self.weight_kg and self.sex and self.birth_date)


def from_form(form) -> tuple[Profile, list[str]]:
    """Reads the "About you" fields. Returns the profile and a list of problems (empty if fine)."""
    problems = []
    profile = Profile()

    def number(field, label, low, high):
        text = (form.get(field) or "").strip()
        try:
            value = float(text)
        except ValueError:
            problems.append(f"Enter your {label}.")
            return None
        if not low <= value <= high:
            problems.append(f"Check your {label}: it should be between {low} and {high}.")
            return None
        return round(value, 1)

    profile.height_cm = number("height_cm", "height in cm", *HEIGHT_CM)
    profile.weight_kg = number("weight_kg", "weight in kg", *WEIGHT_KG)

    profile.sex = form.get("sex", "")
    if profile.sex not in SEXES:
        problems.append("Choose your sex at birth (or \"Prefer not to say\").")
        profile.sex = ""

    profile.birth_date = (form.get("birth_date") or "").strip()
    age = profile.age
    if age is None or not 0 <= age <= 120:
        problems.append("Enter your date of birth.")
        profile.birth_date = ""

    profile.activity = form.get("activity", "")
    if profile.activity not in ACTIVITY:
        profile.activity = ""     # optional

    return profile, problems


def load() -> Profile:
    if not has_request_context():   # e.g. called from a script: there is no visitor
        return Profile()
    saved = session.get(KEY) or {}
    try:
        return Profile(**{k: v for k, v in saved.items() if k in Profile.__dataclass_fields__})
    except TypeError:
        return Profile()


def save(profile: Profile) -> None:
    session[KEY] = asdict(profile)
    session.permanent = True


def delete() -> None:
    session.pop(KEY, None)


def for_ai(profile: Profile) -> dict | None:
    """What the cloud AI may see: age rather than date of birth, and nothing else personal."""
    if not profile.complete:
        return None
    return {
        "age": profile.age,
        "sex_at_birth": SEXES[profile.sex],
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "activity_level": ACTIVITY.get(profile.activity),
    }
