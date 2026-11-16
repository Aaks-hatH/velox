# Velox Health

GitHub repository: `project.1111` — project 48hrs.

A web app that reads Apple Health / Apple Watch data, learns your personal baselines,
highlights statistically unusual changes, and explains them with an assistant.
It does **not** diagnose anything. Demo Mode (fictional data) works straight away.

Built in Python (Flask) so the code is easy to read and present. Everything lives in
[`python-app/`](python-app/README.md).

## Quick start

From the `python-app` folder:

```bash
.venv/bin/python app.py
```

Open http://127.0.0.1:5050 and choose **Demo data** on the last welcome step.
First-time setup, phone access, the AI assistant and a tour of the code are in
[python-app/README.md](python-app/README.md).

## What it does

- **Today:** a live heartbeat line at your resting heart rate, this week's changes, and every measurement with a 14-day trend.
- **Measurement pages:** week, month and 3-month charts with your usual range shaded, plus the evidence and data quality.
- **Patterns:** what changed, what's usual, and where there isn't enough data yet.
- **Ask:** questions answered from your own numbers, on the computer or (optionally) with Claude.
- **Privacy:** no accounts or analytics; an uploaded Health export is kept in memory only.

## How changes are found

Each measurement's last 7 days are compared with the 28 days before ("your usual"), using the
median and median absolute deviation. A change is shown only when it is at least 2× your usual
variation, larger than a small noise floor, and true on at least half of the recent days.
No population "normal ranges" are used.
