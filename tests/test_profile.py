SURVEY = {
    "age": 21,
    "height_cm": 180,
    "weight_kg": 72.5,
    "swim_level": "competitive",
    "sessions_per_week": 5,
    "minutes_per_day": 90,
}


def signup(client):
    client.post(
        "/auth/signup",
        json={"name": "Alice", "email": "alice@example.com", "password": "freestyle50"},
    )


def test_profile_needs_login(client):
    assert client.get("/profile").status_code == 401
    assert client.put("/profile", json=SURVEY).status_code == 401


def test_profile_missing_until_survey_done(client):
    signup(client)
    assert client.get("/profile").status_code == 404


def test_save_and_read_profile(client):
    signup(client)
    res = client.put("/profile", json=SURVEY)
    assert res.status_code == 200
    body = client.get("/profile").json()
    assert {k: body[k] for k in SURVEY} == SURVEY
    assert "updated_at" in body


def test_editing_replaces_answers(client):
    signup(client)
    client.put("/profile", json=SURVEY)
    client.put("/profile", json={**SURVEY, "swim_level": "hobby", "sessions_per_week": 2})
    body = client.get("/profile").json()
    assert body["swim_level"] == "hobby"
    assert body["sessions_per_week"] == 2


def test_profiles_are_per_user(client):
    signup(client)
    client.put("/profile", json=SURVEY)
    client.post(
        "/auth/signup",
        json={"name": "Bob", "email": "bob@example.com", "password": "backstroke100"},
    )
    assert client.get("/profile").status_code == 404


def test_profile_validation(client):
    signup(client)
    for change in [{"age": 2}, {"height_cm": 400}, {"swim_level": "pro"}, {"minutes_per_day": -5}]:
        assert client.put("/profile", json={**SURVEY, **change}).status_code == 422
