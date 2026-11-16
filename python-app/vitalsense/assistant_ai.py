"""
Optional cloud AI assistant, using Anthropic's Claude through the official `anthropic` package.

Privacy rules:
  - Off unless the person turns on "Use cloud AI" in Settings.
  - The API key is read from the ANTHROPIC_API_KEY environment variable on the server.
    It is never sent to the browser and never written into the code.
  - Only a short SUMMARY is sent: for each measurement, its usual value, last-7-day value,
    status and how many days were recorded, plus the "About you" profile as age (not birth
    date), sex at birth, height, weight and activity level. No raw readings, no dates, no export file.
  - Emergencies are handled locally first and never sent anywhere.
  - If anything goes wrong (no key, no internet, limits), the built-in assistant answers instead.

Used by: app.py (the /ask route).
"""

import json
import os

from . import assistant_local, profile
from .analysis import Snapshot
from .assistant_local import Answer
from .metrics import ALL_METRICS, METRICS

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You explain a person's own health-tracker trends in plain, friendly language.

You receive a short summary computed on their device: for each measurement, their usual value \
(median of the previous 4 weeks), the last 7 days, a status, and how many days were recorded. \
Statuses come from a statistical comparison with the person's own history, not from medical norms.
The summary may also include a profile (age, sex at birth, height, weight, activity level). Use it as \
context for suggestions, for example how a step count compares with their stated activity level, \
but not to estimate disease risk.

Rules:
- Use only numbers from the summary. Never invent values, dates or measurements.
- Keep "facts" (what the numbers show), "interpretations" (possible everyday explanations, \
clearly labelled as possibilities) and "limits" (what the data can't tell) separate.
- Never diagnose, name diseases as likely, estimate risk, or give medication or dosage advice. \
If asked, say you can't, and suggest a healthcare professional.
- If the data is demo data, say the values are fictional.
- Keep each list short: at most 4 items, one or two sentences each.
- related_metric is the id of the one measurement the question is mainly about, or "none"."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
        "interpretations": {"type": "array", "items": {"type": "string"}},
        "limits": {"type": "array", "items": {"type": "string"}},
        "related_metric": {"type": "string", "enum": [m.id for m in ALL_METRICS] + ["none"]},
    },
    "required": ["title", "facts", "interpretations", "limits", "related_metric"],
    "additionalProperties": False,
}


def is_configured() -> bool:
    """True when an API key is available on the server."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def summarize(snapshot: Snapshot) -> dict:
    """The ONLY health information that leaves this computer."""
    measurements = []
    for metric in ALL_METRICS:
        a = snapshot.assessments.get(metric.id)
        if a is None:
            continue
        if a.outcome == "unusual":
            status = f"unusual_{a.finding.direction}"
        else:
            status = a.outcome   # "typical" or "insufficient"
        measurements.append({
            "id": metric.id,
            "name": metric.title,
            "unit": metric.unit,
            "status": status,
            "usual_median": round(a.baseline.median, 2) if a.baseline else None,
            "last_7_days_median": round(a.recent.median, 2) if a.recent else None,
            "confidence": a.finding.confidence if a.finding else None,
            "trend_per_week": round(a.trend_per_week, 2) if a.trend_per_week is not None else None,
            "days_recorded_last_5_weeks": a.quality.observed_days,
        })
    summary = {"demo_data": snapshot.is_demo, "measurements": measurements}
    about = profile.for_ai(profile.load())
    if about:
        summary["profile"] = about
    sc = snapshot.sleep_consistency
    if sc:
        summary["sleep_schedule"] = {
            "nights": sc.nights,
            "bedtime_variation_minutes": round(sc.bedtime_spread_minutes),
            "previous_bedtime_variation_minutes":
                round(sc.previous_bedtime_spread_minutes) if sc.previous_bedtime_spread_minutes is not None else None,
        }
    return summary


def answer(question: str, snapshot: Snapshot | None) -> Answer:
    # 1. Emergencies never go to the cloud.
    emergency = assistant_local.safety_check(question)
    if emergency:
        return emergency
    if snapshot is None or not snapshot.series:
        return assistant_local.answer(question, snapshot)

    try:
        import anthropic   # imported here so the rest of the app works even without the package

        client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Summary:\n{json.dumps(summarize(snapshot), indent=1)}\n\nQuestion: {question}",
            }],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
            # If the model declines, the API automatically retries on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            return with_note(assistant_local.answer(question, snapshot), "The cloud AI declined this question.")
        if response.stop_reason == "max_tokens":
            return with_note(assistant_local.answer(question, snapshot), "The cloud AI's answer was cut short.")

        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)
        related = data["related_metric"] if data["related_metric"] in METRICS else None
        return Answer(
            title=data["title"],
            facts=data["facts"],
            interpretations=data["interpretations"],
            limits=data["limits"],
            # The safety note always comes from our own rules, not the model.
            safety_note=assistant_local.safety_note_for(question),
            related_metric=related,
            source="Cloud AI (summary only)",
        )
    except ImportError:
        reason = "The anthropic package isn't installed."
    except Exception as error:   # no key, no internet, rate limit, unexpected reply...
        reason = describe_error(error)
    return with_note(assistant_local.answer(question, snapshot), f"{reason} This answer came from the built-in assistant.")


def describe_error(error: Exception) -> str:
    """Short, plain reason. Never includes health data."""
    import anthropic
    if isinstance(error, anthropic.AuthenticationError):
        return "The cloud AI key was rejected."
    if isinstance(error, anthropic.RateLimitError):
        return "The cloud AI is busy right now."
    if isinstance(error, anthropic.APIConnectionError):
        return "The cloud AI couldn't be reached."
    if isinstance(error, anthropic.APIStatusError):
        return f"The cloud AI returned an error ({error.status_code})."
    if "api_key" in str(error).lower() or "auth" in str(error).lower():
        return "No cloud AI key is set up."
    return "The cloud AI didn't return a usable answer."


def with_note(result: Answer, note: str) -> Answer:
    result.limits.append(note)
    return result
