# Velox Health — Python web app

Velox Health, written in Python so every part is easy to read and explain.
It runs in a browser on your laptop or phone, and can use a cloud AI assistant (Claude)
if you add an API key.

It is not a medical device. It compares your recent data with your own history and never diagnoses.

## Run it

From the `python-app` folder:

```bash
~/.local/bin/uv venv --python 3.12 .venv
```

```bash
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
```

```bash
.venv/bin/python app.py
```

Then open http://127.0.0.1:5050. Choose **Demo data** on the last welcome step to see the full demo story.

**On your phone (same Wi-Fi):** start it with `.venv/bin/python app.py --phone`, find your Mac's address
(System Settings › Wi-Fi › Details › IP address, e.g. 192.168.1.20) and open `http://192.168.1.20:5050`
on the phone. Only do this on a network you trust: anyone on it could open the page.

**Run the tests:**

```bash
.venv/bin/python -m pytest
```

## Turn on the AI assistant (optional)

1. Get an API key at console.anthropic.com (usage is billed per question).
2. Copy `.env.example` to `.env` and paste the key after `ANTHROPIC_API_KEY=`.
3. Restart the app, open **Settings**, turn on **Use cloud AI for answers**, and save.

What gets sent: your question plus a short summary per measurement (usual value, last-7-day value,
status, trend, days recorded). Raw readings, dates and your export file never leave the computer.
Emergency questions are always answered locally. If the key is missing or the internet is down,
the built-in assistant answers instead.

## Use your real Apple Health data

iPhone **Health** app › your picture › **Export All Health Data** › send `export.zip` to your Mac ›
Velox Health **Settings** › **Upload and analyse**. It's read into memory only; stop the app and it's gone.

## How the code is organised

```
python-app/
  app.py                   the web server: one function per page (start here)
  vitalsense/
    metrics.py             the 8 measurements: names, units, colours, noise floors, formatting
    stats.py               median, MAD, Theil–Sen slope (robust statistics)
    analysis.py            "your usual" vs last 7 days → unusual / usual / not enough data
    demo_data.py           fictional 90-day demo data (same story every time)
    health_export.py       reads an Apple Health export.zip into daily values
    charts.py              draws the charts as SVG with plain Python
    assistant_local.py     built-in rule-based assistant + safety rules
    assistant_ai.py        optional Claude assistant (summary only, falls back to local)
    settings.py            saves your choices to data/settings.json
  templates/               the HTML pages (Jinja: HTML with {{ placeholders }})
  static/style.css         colours, fonts, layout, animations
  static/app.js            heartbeat line, chart hover, onboarding steps, chat
  tests/                   37 automatic checks (pytest)
```

**What happens when you open the Today page**

1. The browser asks for `/`. Flask runs `today()` in `app.py`.
2. `current_snapshot()` gets the data: demo data from `demo_data.py`, or your uploaded export.
3. `analysis.build_snapshot()` runs `assess()` on every measurement (see below).
4. `charts.sparkline()` turns the last 14 days into a small SVG line.
5. `render_template("today.html", ...)` fills the HTML template and sends it back.
6. `app.js` starts the heartbeat animation at your resting heart rate.

**How a change gets flagged** (`analysis.assess`)

- Baseline = the 28 days before the last 7. "Your usual" = their median; usual variation = MAD × 1.4826.
- robust z = (last 7 days' median − usual) ÷ usual variation.
- Flagged only if |z| ≥ 2, the change is bigger than the measurement's noise floor (`min_change` in
  `metrics.py`), **and** at least half of the last 7 days are outside the usual range.
- Fewer than 14 baseline days or 4 recent days → "needs more data", with the reason.

**Demo story:** resting heart rate goes up (flagged), sleep goes down (flagged), HRV drifts slowly
(trend only), heart rate has one spike day (correctly not flagged), wrist temperature is missing
recently (needs more data), the rest stay usual.
