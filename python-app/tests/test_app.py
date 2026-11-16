"""Clicks through the web app the way a person would, using Flask's built-in test client."""

import pytest

import app as web
from test_health_export import make_export
from vitalsense import profile, settings

# A filled-in "About you" step, as the onboarding form sends it.
ABOUT = {"height_cm": "178", "weight_kg": "72.5", "sex": "male", "birth_date": "1995-06-01", "activity": "active"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Settings live in each visitor's session cookie. `with` keeps the last request open,
    # so the tests can read settings.load() / profile.load() after a request.
    web.uploaded_snapshot = None
    with web.app.test_client() as test_client:
        yield test_client


def test_new_visitors_are_sent_to_onboarding(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/onboarding" in response.headers["Location"]


def test_onboarding_needs_i_agree(client):
    response = client.post("/onboarding", data={"source": "demo", **ABOUT})
    assert response.status_code == 400
    assert "Please tick" in response.get_data(as_text=True)
    assert not settings.load().onboarded          # still not let in
    assert "/onboarding" in client.get("/").headers["Location"]


def test_demo_flow_shows_every_page(client):
    client.post("/onboarding", data={"agree": "yes", "source": "demo", "resting_hr": "on", "sleep": "on", "steps": "on", **ABOUT})
    today = client.get("/").get_data(as_text=True)
    assert "Demo data" in today and "Two changes worth a look" in today
    for page in ["/patterns", "/ask", "/settings", "/metric/resting_hr?range=W", "/metric/sleep?range=3M"]:
        assert client.get(page).status_code == 200, page
    answer = client.post("/ask", json={"question": "How is my sleep?"}).get_json()
    assert "not connected" in answer["notice"] and "idea representation" in answer["notice"]
    # Emergencies still get real help, even with no AI model connected.
    urgent = client.post("/ask", json={"question": "I have chest pain"}).get_json()
    assert urgent["title"] == "Please get help now"


def test_upload_switches_to_real_data(client):
    client.post("/onboarding", data={"agree": "yes", "source": "export", "resting_hr": "on", "steps": "on", **ABOUT})
    response = client.post("/upload", data={"export": (make_export(), "export.zip")},
                           content_type="multipart/form-data")
    assert response.status_code == 302
    today = client.get("/").get_data(as_text=True)
    assert "Demo data" not in today and "Resting HR" in today


def test_delete_returns_to_onboarding(client):
    client.post("/onboarding", data={"agree": "yes", "source": "demo", **ABOUT})
    client.post("/delete-data")
    assert not settings.load().onboarded
    assert "/onboarding" in client.get("/").headers["Location"]


def test_ask_ai_is_on_every_page_and_overview_on_today(client):
    client.post("/onboarding", data={"agree": "yes", "source": "demo", **ABOUT})
    for page in ["/", "/patterns", "/settings", "/metric/sleep"]:
        assert "data-ask-dock" in client.get(page).get_data(as_text=True), page
    assert "data-ask-dock" not in client.get("/ask").get_data(as_text=True)   # Ask has its own box
    today = client.get("/").get_data(as_text=True)
    assert "AI overview" in today and "/ask?q=" in today
    assert "How has my sleep duration changed this week?" in client.get("/metric/sleep").get_data(as_text=True)


def test_greeting_uses_the_name_from_settings(client):
    client.post("/onboarding", data={"source": "demo", "agree": "yes", **ABOUT})
    client.post("/settings", data={"name": "  Chris  ", "demo_mode": "on"})
    assert settings.load().name == "Chris"
    page = client.get("/").get_data(as_text=True)
    assert "Chris</h1>" in page
    client.post("/settings", data={"name": "", "demo_mode": "on"})
    assert "Chris</h1>" not in client.get("/").get_data(as_text=True)


def test_onboarding_needs_about_you_and_saves_it(client):
    response = client.post("/onboarding", data={"agree": "yes", "name": "Sam", "height_cm": "abc"})
    assert response.status_code == 400 and "Enter your height" in response.get_data(as_text=True)
    assert not settings.load().onboarded
    client.post("/onboarding", data={"agree": "yes", "name": "Sam", **ABOUT})
    saved = profile.load()
    assert settings.load().onboarded and settings.load().name == "Sam"
    assert saved.height_cm == 178 and saved.weight_kg == 72.5 and saved.sex == "male" and saved.age >= 30


def test_sign_up_email_and_password_are_never_sent(client):
    page = client.get("/onboarding").get_data(as_text=True)
    assert 'type="email" autocomplete' in page and 'name="email"' not in page and 'name="password"' not in page


def test_ai_summary_gets_age_not_birth_date(client):
    from vitalsense import assistant_ai
    client.post("/onboarding", data={"agree": "yes", "source": "demo", **ABOUT})
    summary = assistant_ai.summarize(web.current_snapshot())
    assert summary["profile"]["height_cm"] == 178 and "age" in summary["profile"]
    assert "1995" not in str(summary)


def test_skip_goes_straight_into_the_app(client):
    response = client.post("/onboarding", data={"skip": "yes", "name": "Sam"})
    assert response.status_code == 302 and response.headers["Location"].endswith("/")
    assert settings.load().onboarded and settings.load().demo_mode
    assert client.get("/").status_code == 200


def test_each_visitor_has_their_own_settings():
    first, second = web.app.test_client(), web.app.test_client()
    first.post("/onboarding", data={"agree": "yes", "name": "Ana", **ABOUT})
    assert "Ana</h1>" in first.get("/").get_data(as_text=True)
    assert "/onboarding" in second.get("/").headers["Location"]     # a new visitor starts fresh


def test_public_demo_turns_off_uploads(client, monkeypatch):
    monkeypatch.setattr(web, "PUBLIC_DEMO", True)
    client.post("/onboarding", data={"agree": "yes", **ABOUT})
    zip_bytes = make_export()
    response = client.post("/upload", data={"export": (zip_bytes, "export.zip")})
    assert "switched+off" in response.headers["Location"] or "switched%20off" in response.headers["Location"]
    assert web.uploaded_snapshot is None
