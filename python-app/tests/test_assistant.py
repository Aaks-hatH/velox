from conftest import NOW
from vitalsense import assistant_ai, assistant_local
from vitalsense.demo_data import demo_snapshot
from vitalsense.metrics import METRICS, format_value

SNAPSHOT = demo_snapshot(NOW)


def test_demo_data_tells_the_intended_story():
    a = SNAPSHOT.assessments
    assert a["resting_hr"].finding.direction == "up"
    assert a["sleep"].finding.direction == "down"
    assert a["heart_rate"].finding is None, "single spike day must not be flagged"
    assert a["wrist_temp"].outcome == "insufficient"
    assert a["breathing"].finding is None
    assert a["hrv"].trend_per_week < 0
    assert SNAPSHOT.sleep_consistency is not None


def test_detects_metrics_without_confusing_heart_rates():
    assert assistant_local.detect_metric("how has my resting heart rate changed").id == "resting_hr"
    assert assistant_local.detect_metric("what about heart rate variability").id == "hrv"
    assert assistant_local.detect_metric("my heart rate today").id == "heart_rate"
    assert assistant_local.detect_metric("did i sleep well").id == "sleep"
    assert assistant_local.detect_metric("hello there") is None


def test_metric_answer_uses_only_measured_numbers():
    a = assistant_local.answer("How has my resting heart rate changed this week?", SNAPSHOT)
    assert a.related_metric == "resting_hr"
    median = format_value(METRICS["resting_hr"], SNAPSHOT.assessments["resting_hr"].recent.median)
    assert any(median in fact for fact in a.facts)
    assert any("Demo Mode" in limit for limit in a.limits)
    assert a.safety_note is None


def test_refuses_diagnosis_but_still_shows_facts():
    a = assistant_local.answer("Do I have a heart disease?", SNAPSHOT)
    assert "can't diagnose" in a.safety_note
    assert a.facts


def test_refuses_medication_advice():
    a = assistant_local.answer("Should I take medication for my resting heart rate?", SNAPSHOT)
    assert "medication" in a.safety_note


def test_emergency_words_get_safety_message():
    a = assistant_local.answer("I have chest pain", None)
    assert "emergency" in a.safety_note


def test_no_data_never_invents_values():
    assert "No measurements" in assistant_local.answer("How is my sleep?", None).title


def test_overview_lists_changed_metrics():
    a = assistant_local.answer("Which measurements have changed recently?", SNAPSHOT)
    assert any("Resting Heart Rate" in fact for fact in a.facts)
    assert any("Sleep Duration" in fact for fact in a.facts)
    assert any("Wrist Temp" in limit for limit in a.limits)


def test_sleep_consistency_question():
    a = assistant_local.answer("Has my sleep schedule been consistent?", SNAPSHOT)
    assert a.title == "Sleep schedule"
    assert any("less regular" in i for i in a.interpretations)


def test_data_sufficiency_question():
    a = assistant_local.answer("Do I have enough data to understand this trend?", SNAPSHOT)
    assert any("Wrist Temp" in fact and "not enough" in fact for fact in a.facts)


def test_ai_summary_contains_no_raw_readings():
    summary = assistant_ai.summarize(SNAPSHOT)
    assert summary["demo_data"] is True
    keys = set(summary["measurements"][0])
    assert keys == {"id", "name", "unit", "status", "usual_median", "last_7_days_median",
                    "confidence", "trend_per_week", "days_recorded_last_5_weeks"}


def test_ai_never_sends_emergencies(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    a = assistant_ai.answer("I think I'm having a heart attack", SNAPSHOT)
    assert a.title == "Please get help now"


def test_ai_falls_back_to_local_when_key_is_wrong(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9")   # nothing listens here: fails fast
    a = assistant_ai.answer("How is my sleep?", SNAPSHOT)
    assert a.source == "On-device"
    assert "built-in assistant" in a.limits[-1]
