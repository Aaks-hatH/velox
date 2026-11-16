"""
The built-in assistant. Runs entirely inside this app, with no internet and no AI service.

It recognises what a question is about (a measurement, sleep schedule, "enough data?",
an overview) and builds an answer ONLY from numbers that were actually measured or
calculated. It never invents values.

Every answer keeps three things separate:
  - facts:            what the data shows (numbers only)
  - interpretations:  what it could mean (clearly labelled possibilities)
  - limits:           what it can't tell you

Safety rules run first: emergencies get an emergency message, and questions asking for a
diagnosis or medication advice get a clear "I can't do that" note.

Used by: app.py (the /ask route) and assistant_ai.py (as a fallback and for safety checks).
"""

from dataclasses import dataclass, field
from datetime import timedelta

from . import stats
from .analysis import Snapshot
from .metrics import ALL_METRICS, METRICS, Metric, format_change, format_value

SUGGESTED_QUESTIONS = [
    "Which measurements have changed recently?",
    "How has my resting heart rate changed this week?",
    "Has my sleep schedule been consistent?",
    "Do I have enough data to understand my trends?",
    "How are my steps this week?",
    "What's happening with my HRV?",
]

EMERGENCY_WORDS = ["chest pain", "can't breathe", "cannot breathe", "trouble breathing", "fainted",
                   "passed out", "stroke", "heart attack", "emergency", "suicid", "kill myself"]
DIAGNOSIS_WORDS = ["diagnos", "disease", "do i have", "am i sick", "illness", "condition", "cancer",
                   "covid", "infection", "afib", "atrial", "arrhythmia", "diabetes", "pregnan",
                   "risk of", "chance of", "probability", "is it serious", "dangerous", "normal?"]
MEDICATION_WORDS = ["medic", "dose", "dosage", "pill", "prescri", "drug", "beta blocker",
                    "should i stop taking", "should i take", "supplement"]

DEMO_NOTE = "These are fictional Demo Mode values, not real measurements."
DIAGNOSIS_NOTE = ("I can't diagnose conditions or estimate the chance of a disease. These are comparisons "
                  "with your own past measurements. If you're worried about your health, a healthcare "
                  "professional can properly assess it.")
MEDICATION_NOTE = ("I can't give advice about medication. Please don't start, stop, or change any medicine "
                   "based on these numbers. Talk to your doctor or pharmacist.")
EMERGENCY_NOTE = ("If you feel unwell right now or think this could be an emergency, call your local "
                  "emergency number or seek urgent medical care. If you're having thoughts of harming "
                  "yourself, contact a crisis line in your country.")


@dataclass
class Answer:
    title: str
    facts: list[str] = field(default_factory=list)
    interpretations: list[str] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    safety_note: str | None = None
    related_metric: str | None = None    # metric id, used for an "Open chart" link
    source: str = "On-device"            # shown under the answer
    notice: str | None = None            # a plain message shown instead of the lists


def contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def detect_metric(question: str) -> Metric | None:
    """First measurement whose keywords appear in the question (see ALL_METRICS for the order)."""
    q = question.lower()
    for metric in ALL_METRICS:
        if contains_any(q, list(metric.keywords)):
            return metric
    return None


def safety_check(question: str) -> Answer | None:
    """Returns an emergency answer if needed. Used before anything else, including the cloud AI."""
    if contains_any(question.lower(), EMERGENCY_WORDS):
        return Answer(title="Please get help now",
                      facts=["Velox Health can't assess symptoms or emergencies."],
                      safety_note=EMERGENCY_NOTE)
    return None


def safety_note_for(question: str) -> str | None:
    q = question.lower()
    if contains_any(q, MEDICATION_WORDS):
        return MEDICATION_NOTE
    if contains_any(q, DIAGNOSIS_WORDS):
        return DIAGNOSIS_NOTE
    return None


def answer(question: str, snapshot: Snapshot | None) -> Answer:
    emergency = safety_check(question)
    if emergency:
        return emergency

    q = question.lower()
    metric = detect_metric(q)

    if snapshot is None or not snapshot.series:
        return Answer(title="No measurements loaded yet",
                      facts=["There's no data to look at yet. Upload an Apple Health export or turn on "
                             "Demo Mode in Settings."],
                      limits=["I only answer from measurements that have actually been loaded. "
                              "I never guess missing values."])

    # Pick the kind of answer from the wording of the question.
    if contains_any(q, ["consistent", "schedule", "regular", "bedtime", "routine", "wake up", "wake time"]) \
            and (metric is None or metric.id == "sleep"):
        result = sleep_schedule_answer(snapshot)
    elif contains_any(q, ["enough data", "enough information", "reliable", "trust", "how much data",
                          "confiden", "accurate"]):
        result = data_answer(snapshot, metric)
    elif metric:
        result = metric_answer(metric, snapshot)
    elif contains_any(q, ["change", "unusual", "different", "stand out", "overview", "summary", "how am i",
                          "anything", "notice", "pattern", "week", "doing", "health"]) \
            or contains_any(q, DIAGNOSIS_WORDS):
        result = overview_answer(snapshot)
    else:
        result = help_answer()

    result.safety_note = safety_note_for(question)
    return result


# ----------------------------------------------------------------------------
# The different kinds of answer
# ----------------------------------------------------------------------------

def metric_answer(metric: Metric, snapshot: Snapshot) -> Answer:
    series = snapshot.series.get(metric.id)
    if series is None:
        return Answer(title=metric.title, related_metric=metric.id,
                      facts=[f"{metric.title} is turned off in Settings, so it hasn't been loaded."])

    assessment = snapshot.assessments.get(metric.id)
    latest = series.latest
    if latest is None:
        return Answer(title=metric.title, related_metric=metric.id,
                      facts=[f"I don't have any {metric.title.lower()} readings to work with."],
                      limits=(assessment.quality.issues if assessment else [])
                      + ["No data doesn't tell us whether access was off or nothing was recorded."])

    facts = [f"Most recent daily value: {format_value(metric, latest.value)} {day_label(latest.day, snapshot)}."]
    if assessment and assessment.recent:
        r = assessment.recent
        facts.append(f"Last {r.expected_days} days: median {format_value(metric, r.median)}, ranging "
                     f"{format_value(metric, r.min, False)}–{format_value(metric, r.max)} "
                     f"({r.count} of {r.expected_days} days recorded).")
    if assessment and assessment.baseline:
        b = assessment.baseline
        facts.append(f"Your previous {b.expected_days} days: median {format_value(metric, b.median)} "
                     f"({b.count} days recorded).")
    week = week_over_week(metric, snapshot)
    if week:
        this_week, last_week = week
        facts.append(f"Compared with the week before: {format_change(metric, this_week - last_week)} "
                     f"(average {format_value(metric, this_week)} vs {format_value(metric, last_week)}).")
    if assessment and assessment.trend_per_week is not None:
        trend = assessment.trend_per_week
        if abs(trend * 5) < metric.min_change / 2:
            facts.append("Over the last 5 weeks the overall trend is essentially flat.")
        else:
            facts.append(f"Over the last 5 weeks the overall trend is about {format_change(metric, trend)} per week.")

    interpretations, limits = [], []
    if assessment and assessment.outcome == "unusual":
        f = assessment.finding
        how = "clearly" if f.is_strong else "noticeably"
        strength = "strong" if f.is_strong else "notable"
        interpretations += [
            f"This week is {how} {f.word} than your usual, a statistically {strength} difference "
            f"({f.confidence} confidence).",
            f"Possible everyday factors (not a diagnosis): {metric.everyday_factors}.",
            "If the change continues or you feel unwell, it may be worth mentioning to a healthcare professional.",
        ]
        limits = list(f.limitations)
    elif assessment and assessment.outcome == "typical":
        interpretations.append("Your recent values are within your usual range. Nothing here stands out statistically.")
        limits = assessment.quality.issues + [
            "Being within your usual range doesn't rule anything out. It only means no unusual change was detected."]
    elif assessment:
        interpretations.append("I can't judge whether this has changed yet.")
        limits = [assessment.reason] + assessment.quality.issues
    if snapshot.is_demo:
        limits.append(DEMO_NOTE)

    return Answer(metric.title, facts, interpretations, limits, related_metric=metric.id)


def overview_answer(snapshot: Snapshot) -> Answer:
    ordered = [snapshot.assessments[m.id] for m in ALL_METRICS if m.id in snapshot.assessments]
    unusual = [a.finding for a in ordered if a.outcome == "unusual"]
    typical = [a for a in ordered if a.outcome == "typical"]
    insufficient = [a for a in ordered if a.outcome == "insufficient"]

    facts = []
    if not unusual:
        facts.append("No measurement shows a statistically unusual change this week compared with your own history.")
    for f in unusual:
        m = f.metric
        facts.append(f"{m.title}: {f.word} than usual, {format_value(m, f.recent.median)} vs your usual "
                     f"{format_value(m, f.baseline.median)} ({format_change(m, f.change)}, {f.confidence} confidence).")
    if typical:
        facts.append("Within your usual range: " + ", ".join(a.metric.short_title for a in typical) + ".")

    limits = []
    if insufficient:
        limits.append("Not enough data to judge: " + ", ".join(a.metric.short_title for a in insufficient) + ".")
    limits.append("Each measurement is compared only with your own previous 4 weeks. No population averages are used.")
    if snapshot.is_demo:
        limits.append(DEMO_NOTE)

    interpretations = []
    if unusual:
        interpretations.append("Short-term changes are common and often reflect sleep, stress, travel, activity, "
                               "or illness. A change on its own isn't a diagnosis. The Patterns page shows the evidence.")

    if not unusual:
        title = "No unusual changes"
    elif len(unusual) == 1:
        title = "1 measurement changed"
    else:
        title = f"{len(unusual)} measurements changed"
    return Answer(title, facts, interpretations, limits)


def sleep_schedule_answer(snapshot: Snapshot) -> Answer:
    sc = snapshot.sleep_consistency
    if sc is None:
        return Answer("Sleep schedule", related_metric="sleep",
                      facts=["There aren't enough recorded nights (at least 5 in the last 2 weeks) to describe "
                             "your sleep schedule."],
                      limits=["Sleep needs to be tracked with Apple Watch or another sleep source in the Health app."])

    facts = [
        f"Over your last {sc.nights} recorded nights you usually fell asleep around {clock(sc.average_bedtime)} "
        f"and woke around {clock(sc.average_wake)}.",
        f"Bedtime varied by about ±{round(sc.bedtime_spread_minutes)} min; wake time by about "
        f"±{round(sc.wake_spread_minutes)} min.",
    ]
    interpretations = []
    if sc.previous_bedtime_spread_minutes is not None:
        previous = sc.previous_bedtime_spread_minutes
        facts.append(f"In the two weeks before, bedtime varied by about ±{round(previous)} min.")
        difference = sc.bedtime_spread_minutes - previous
        if difference > 15:
            interpretations.append("Your bedtime has been less regular recently than before.")
        elif difference < -15:
            interpretations.append("Your bedtime has been more regular recently than before.")
        else:
            interpretations.append("Your bedtime regularity is similar to the previous two weeks.")

    sleep = snapshot.assessments.get("sleep")
    if sleep and sleep.finding:
        f = sleep.finding
        facts.append(f"Sleep duration has also been {f.word} than usual: {format_value(f.metric, f.recent.median)} "
                     f"vs {format_value(f.metric, f.baseline.median)}.")
    limits = ["Times are based on when your devices recorded you as asleep, which may differ from when you went to bed."]
    if snapshot.is_demo:
        limits.append(DEMO_NOTE)
    return Answer("Sleep schedule", facts, interpretations, limits, related_metric="sleep")


def data_answer(snapshot: Snapshot, metric: Metric | None) -> Answer:
    metrics = [metric] if metric else [m for m in ALL_METRICS if m.id in snapshot.assessments]
    facts, limits = [], []
    for m in metrics:
        a = snapshot.assessments.get(m.id)
        if a is None:
            continue
        if a.outcome == "insufficient":
            status = "not enough yet"
            limits.append(f"{m.short_title}: {a.reason}")
        else:
            status = "enough to compare"
        facts.append(f"{m.short_title}: {a.quality.observed_days} of {a.quality.expected_days} days recorded "
                     f"in the last 5 weeks, {status}.")
    return Answer(
        title=f"Data for {metric.short_title}" if metric else "How much data there is",
        facts=facts,
        interpretations=["A personal baseline needs at least 14 days in the previous 4 weeks, plus at least "
                         "4 days this week. More days make comparisons more reliable."],
        limits=limits + ["Missing days are never filled in with estimates."],
        related_metric=metric.id if metric else None)


def help_answer() -> Answer:
    return Answer(
        title="Here's what I can help with",
        facts=["How a specific measurement has changed (resting heart rate, HRV, heart rate, breathing rate, "
               "sleep, wrist temperature, steps, distance).",
               "Which measurements have changed recently.",
               "Whether your sleep schedule has been consistent.",
               "Whether there's enough data to understand a trend."],
        limits=["I answer from your loaded measurements only. I can't diagnose, predict disease, "
                "or advise on medication."])


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def week_over_week(metric: Metric, snapshot: Snapshot) -> tuple[float, float] | None:
    """Average of the last 7 days and the 7 before. None if either week has fewer than 3 days."""
    series = snapshot.series[metric.id]
    today = snapshot.generated_at.date()
    end = today if metric.today_is_partial else today + timedelta(days=1)
    this_start = end - timedelta(days=7)
    previous_start = end - timedelta(days=14)
    this_week = [d.value for d in series.days if this_start <= d.day < end]
    previous_week = [d.value for d in series.days if previous_start <= d.day < this_start]
    if len(this_week) < 3 or len(previous_week) < 3:
        return None
    return stats.mean(this_week), stats.mean(previous_week)


def day_label(day, snapshot: Snapshot) -> str:
    today = snapshot.generated_at.date()
    if day == today:
        return "today"
    if day == today - timedelta(days=1):
        return "yesterday"
    return "on " + day.strftime("%A %-d %B")


def clock(hour_minute: tuple[int, int]) -> str:
    hour, minute = hour_minute
    suffix = "am" if hour < 12 else "pm"
    return f"{(hour % 12) or 12}:{minute:02d} {suffix}"


def metric_by_id(metric_id: str | None) -> Metric | None:
    return METRICS.get(metric_id) if metric_id else None
