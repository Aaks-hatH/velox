"""
The web server. Run it with:   .venv/bin/python app.py   then open http://127.0.0.1:5050

Flask works like this: each function below is linked to a web address with @app.route.
When the browser asks for that address, Flask runs the function and sends back what it
returns, usually an HTML page built from a template in the templates/ folder.

Pages:  /onboarding  /  (Today)  /metric/<id>  /patterns  /ask  /settings
Actions: POST /ask (question -> answer as JSON), POST /settings, POST /upload, POST /delete-data
"""

import os
import secrets
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, redirect, render_template, request, url_for

from vitalsense import assistant_ai, assistant_local, charts, health_export, profile, settings
from vitalsense.demo_data import demo_snapshot
from vitalsense.metrics import ALL_METRICS, METRICS, format_change, format_hours, format_value


def load_env_file() -> None:
    """Reads KEY=value lines from python-app/.env (where you put ANTHROPIC_API_KEY). Never committed."""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_file):
        return
    with open(env_file) as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_env_file()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024**3    # Health exports can be large

# PUBLIC_DEMO=1 when the app is online for anyone with the link (see render.yaml).
# Then it only shows demo data: real Health exports can't be uploaded to a shared server.
PUBLIC_DEMO = os.environ.get("PUBLIC_DEMO") == "1"


def secret_key() -> str:
    """Signs each visitor's settings cookie so it can't be tampered with.
    Online it comes from the SECRET_KEY environment variable; on this computer it is made once
    and kept in data/secret_key (never committed)."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "secret_key")
    if not os.path.exists(key_file):
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        with open(key_file, "w") as file:
            file.write(secrets.token_hex(32))
        os.chmod(key_file, 0o600)
    with open(key_file) as file:
        return file.read().strip()


app.secret_key = secret_key()
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=90),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PUBLIC_DEMO,    # online the site is HTTPS only
)

# A real Health export is kept only in memory: it disappears when the server stops.
uploaded_snapshot = None

RANGES = {"W": 7, "M": 30, "3M": 90}


def current_snapshot():
    """The data every page shows: demo data, or the uploaded export."""
    choices = settings.load()
    if choices.demo_mode or PUBLIC_DEMO:
        return demo_snapshot(datetime.now(), choices.enabled_metrics)
    return uploaded_snapshot


# Make these available inside every template.
@app.context_processor
def template_helpers():
    return {"fmt": format_value, "fmt_change": format_change, "fmt_hours": format_hours,
            "METRICS": METRICS, "settings": settings.load(), "status_text": status_text}


@app.before_request
def require_onboarding():
    """Until onboarding is finished, every page sends you to it."""
    allowed = ("onboarding", "static", "delete_data")
    if request.endpoint not in allowed and not settings.load().onboarded:
        return redirect(url_for("onboarding"))


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------

def onboarding_page(choices, about, **errors):
    return render_template("onboarding.html", choices=choices, profile=about,
                           sexes=profile.SEXES, activity=profile.ACTIVITY,
                           today_iso=date.today().isoformat(), **errors)


@app.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    """Get started → Sign up (for show) → About you → Agree and proceed."""
    choices = settings.load()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:40]
        if name:
            choices.name = name
        if request.form.get("skip") == "yes":
            # For showing the idea: straight into the app with demo data (any saved profile is kept).
            choices.onboarded = True
            choices.demo_mode = True
            settings.save(choices)
            return redirect(url_for("today"))
        about, problems = profile.from_form(request.form)
        # Checked here as well as on the page, so nothing can be skipped (e.g. with JavaScript off).
        if problems:
            return onboarding_page(choices, about, profile_errors=problems), 400
        if request.form.get("agree") != "yes":
            return onboarding_page(choices, about, agree_error=True), 400
        profile.save(about)
        # Measurements and data source start as "all" and "demo"; both can be changed in Settings.
        picked = [m.id for m in ALL_METRICS if request.form.get(m.id)]
        choices.enabled_metrics = picked or choices.enabled_metrics
        choices.demo_mode = request.form.get("source") != "export"
        choices.onboarded = True
        settings.save(choices)
        return redirect(url_for("settings_page") if not choices.demo_mode else url_for("today"))
    return onboarding_page(choices, profile.load())


@app.route("/")
def today():
    snapshot = current_snapshot()
    rows = []
    if snapshot:
        for metric in ALL_METRICS:
            series = snapshot.series.get(metric.id)
            if series is None:
                continue
            rows.append({
                "metric": metric,
                "latest": series.latest,
                "assessment": snapshot.assessments[metric.id],
            })
    resting = snapshot.series.get("resting_hr") if snapshot else None
    # A short summary from the assistant, shown under the solar system.
    overview = assistant_local.overview_answer(snapshot) if snapshot else None
    return render_template("today.html", snapshot=snapshot, rows=rows, overview=overview,
                           resting_bpm=round(resting.latest.value) if resting and resting.latest else None,
                           greeting=greeting(settings.load().name), now=datetime.now())


@app.route("/metric/<metric_id>")
def metric_page(metric_id):
    metric = METRICS.get(metric_id)
    snapshot = current_snapshot()
    if metric is None or snapshot is None or metric_id not in snapshot.series:
        return redirect(url_for("today"))

    chosen_range = request.args.get("range", "M")
    if chosen_range not in RANGES:
        chosen_range = "M"
    series = snapshot.series[metric_id]
    assessment = snapshot.assessments[metric_id]
    first_day = snapshot.generated_at.date() - timedelta(days=RANGES[chosen_range] - 1)
    shown = [d for d in series.days if d.day >= first_day]
    chart = charts.detail_chart(shown, metric, assessment.baseline)
    average = sum(d.value for d in shown) / len(shown) if shown else None

    nights = list(reversed(snapshot.sleep_nights[-7:])) if metric_id == "sleep" else []
    return render_template("metric.html", metric=metric, series=series, assessment=assessment,
                           chart=chart, range=chosen_range, ranges=RANGES, average=average,
                           nights=nights, snapshot=snapshot, trend=trend_text(metric, assessment))


@app.route("/patterns")
def patterns():
    snapshot = current_snapshot()
    groups = {"unusual": [], "typical": [], "insufficient": []}
    if snapshot:
        for metric in ALL_METRICS:
            if metric.id in snapshot.assessments:
                assessment = snapshot.assessments[metric.id]
                groups[assessment.outcome].append(assessment)
    return render_template("patterns.html", snapshot=snapshot, groups=groups)


NOT_CONNECTED = assistant_local.Answer(
    title="The AI model isn't connected yet",
    notice="The API for the AI model is not connected. Velox Health is ready to connect to one "
           "(add an API key to switch it on), but this version was built just for idea representation.",
    source="Velox Health",
)


@app.route("/ask", methods=["GET", "POST"])
def ask():
    if request.method == "GET":
        return render_template("ask.html", questions=assistant_local.SUGGESTED_QUESTIONS,
                               ai_ready=assistant_ai.is_configured())
    question = (request.get_json(silent=True) or {}).get("question", "").strip()[:500]
    if not question:
        return jsonify({"error": "Type a question first."}), 400
    snapshot = current_snapshot()
    if settings.load().ai_consent and assistant_ai.is_configured():
        result = assistant_ai.answer(question, snapshot)
    else:
        # No AI model connected: emergencies still get help straight away, everything else
        # gets a note that this version only represents the idea.
        result = assistant_local.safety_check(question) or NOT_CONNECTED
    data = asdict(result)
    if result.related_metric:
        data["related_url"] = url_for("metric_page", metric_id=result.related_metric)
        data["related_name"] = METRICS[result.related_metric].short_title
    return jsonify(data)


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    choices = settings.load()
    if request.method == "POST":
        choices.name = request.form.get("name", "").strip()[:40]
        problems = []
        if any(request.form.get(k) for k in ("height_cm", "weight_kg", "sex", "birth_date")):
            about, problems = profile.from_form(request.form)
            if not problems:
                profile.save(about)
        choices.demo_mode = request.form.get("demo_mode") == "on"
        choices.ai_consent = request.form.get("ai_consent") == "on"
        picked = [m.id for m in ALL_METRICS if request.form.get(m.id)]
        if picked:
            choices.enabled_metrics = picked
        settings.save(choices)
        if problems:   # everything else is saved; the profile waits until it's fixed
            return redirect(url_for("settings_page", message="Profile not saved. " + " ".join(problems)))
        return redirect(url_for("settings_page", saved=1))
    return render_template("settings.html", choices=choices, metrics=ALL_METRICS,
                           has_upload=uploaded_snapshot is not None, public_demo=PUBLIC_DEMO,
                           ai_ready=assistant_ai.is_configured(),
                           profile=profile.load(), sexes=profile.SEXES, activity=profile.ACTIVITY,
                           message=request.args.get("message"), saved=request.args.get("saved"))


@app.route("/upload", methods=["POST"])
def upload():
    global uploaded_snapshot
    if PUBLIC_DEMO:
        return redirect(url_for("settings_page", message="Uploads are switched off in the online demo. It shows demo data only."))
    file = request.files.get("export")
    if not file or not file.filename:
        return redirect(url_for("settings_page", message="Choose your export.zip file first."))
    try:
        choices = settings.load()
        uploaded_snapshot = health_export.load_export(file.stream, datetime.now(), choices.enabled_metrics)
    except health_export.ExportError as error:
        return redirect(url_for("settings_page", message=str(error)))
    choices.demo_mode = False
    settings.save(choices)
    return redirect(url_for("today"))


@app.route("/delete-data", methods=["POST"])
def delete_data():
    global uploaded_snapshot
    uploaded_snapshot = None
    settings.delete_all()
    profile.delete()
    return redirect(url_for("onboarding"))


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def greeting(name: str = "") -> str:
    """"Good morning Chris", "Hello Chris"... or just the greeting if no name is set."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        word = "Good morning"
    elif 12 <= hour < 17:
        word = "Good afternoon"
    elif 17 <= hour < 22:
        word = "Good evening"
    else:
        word = "Hello"
    return f"{word} {name}".strip()


def status_text(assessment) -> str:
    """Plain words for a measurement's result, read out by screen readers."""
    if assessment.outcome == "unusual":
        return f"{assessment.finding.word} than usual"
    if assessment.outcome == "typical":
        return "within your usual range"
    return "not enough data yet"


def trend_text(metric, assessment) -> str:
    if assessment.trend_per_week is None:
        return "—"
    if abs(assessment.trend_per_week * 5) < metric.min_change / 2:
        return "Flat"
    return f"{format_change(metric, assessment.trend_per_week)}/wk"


if __name__ == "__main__":
    # 127.0.0.1 = only this computer can open it. Add --phone to allow devices on your Wi-Fi.
    host = "0.0.0.0" if "--phone" in sys.argv else "127.0.0.1"
    port = int(os.environ.get("PORT", 5050))
    app.run(host=host, port=port, debug="--debug" in sys.argv)
