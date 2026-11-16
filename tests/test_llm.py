"""The optional OpenAI rewording layer: the adapter, the plan validator, and the fallback.

No request ever leaves this machine. The adapter is driven through the real OpenAI SDK with
a fake HTTP transport, so the request it builds is the real one, and every answer is a
mocked one. These tests say nothing about the quality of a real model's wording."""
# ruff: noqa: E501  (long fixture lines are kept whole)

import json
import logging
from datetime import date

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from firebase_admin import auth
from test_training import MON, NO_ISSUE, SUPPORTED, UID, add_video, profile, week

from aquatrack.analysis import explain
from aquatrack.analysis.explain import ExplainError, OpenAIExplainer, Rejected
from aquatrack.api import firebase, main, training
from aquatrack.api.jobs import InlineRunner
from aquatrack.api.store import MemoryStore
from aquatrack.training.explain import (
    SCHEMA,
    SYSTEM,
    build_plan_payload,
    explain_plan,
    validate_plan,
)

SECRET = "sk-test-secret-never-real"
# Everything except the reworded text and its record: what a rewording may never change.
KEEP = {"explained": True, "explanation": True, "sessions": {"__all__": {"explained"}}}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any attempt to open a real connection fails the test."""

    def refuse(*a, **k):
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", refuse)
    for name in (
        "AQUATRACK_LLM_PROVIDER",
        "AQUATRACK_LLM_MODEL",
        "AQUATRACK_LLM",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def api_response(text=None, status="completed", refusal=None, incomplete=None):
    """A Responses API body, as the SDK receives it. MOCKED."""
    part = (
        {"type": "refusal", "refusal": refusal}
        if refusal
        else {"type": "output_text", "text": text, "annotations": []}
    )
    return {
        "id": "resp_mock",
        "object": "response",
        "created_at": 0,
        "status": status,
        "model": "gpt-6-luna",
        "incomplete_details": {"reason": incomplete} if incomplete else None,
        "output": [
            {
                "type": "message",
                "id": "msg_mock",
                "role": "assistant",
                "status": "completed",
                "content": [part],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def explainer(handler, **kw) -> OpenAIExplainer:
    client = openai.OpenAI(
        api_key=SECRET,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )
    return OpenAIExplainer(client=client, **kw)


def answering(body, seen=None, status_code=200):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status_code, json=body)

    return handler


# ---------- the adapter ----------


def test_the_request_uses_the_responses_api_with_a_strict_schema_and_bounded_output():
    seen = []
    plan = week()
    out = explainer(answering(api_response('{"summary": "ok", "sessions": []}'), seen)).complete(
        "plan_rewording", SYSTEM, SCHEMA, build_plan_payload(plan)
    )
    assert out == {"summary": "ok", "sessions": []}
    (request,) = seen
    assert request.method == "POST" and request.url.path.endswith("/responses")
    body = json.loads(request.content)
    assert body["model"] == explain.DEFAULT_MODEL == "gpt-6-luna"
    assert body["instructions"] == SYSTEM
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "plan_rewording",
        "schema": SCHEMA,
        "strict": True,
    }
    assert body["max_output_tokens"] == explain.DEFAULT_MAX_OUTPUT_TOKENS
    assert body["store"] is False and body["reasoning"] == {"effort": "low"}
    assert json.loads(body["input"]) == json.loads(json.dumps(build_plan_payload(plan)))
    assert "temperature" not in body and "tools" not in body


def test_strict_schemas_list_every_property_as_required_and_allow_nothing_else():
    def check(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert sorted(node["required"]) == sorted(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])

    check(SCHEMA)
    check(explain.SCHEMA)


def test_model_timeout_and_limits_come_from_configuration(monkeypatch):
    monkeypatch.setenv("AQUATRACK_LLM_MODEL", "gpt-6.1-terra")
    monkeypatch.setenv("AQUATRACK_LLM_MAX_OUTPUT_TOKENS", "900")
    monkeypatch.setenv("AQUATRACK_LLM_REASONING", "")
    seen = []
    e = explainer(answering(api_response("{}"), seen))
    e.complete("x", "s", {"type": "object"}, {})
    body = json.loads(seen[0].content)
    assert (e.model, body["model"], body["max_output_tokens"]) == (
        "gpt-6.1-terra",
        "gpt-6.1-terra",
        900,
    )
    assert "reasoning" not in body
    monkeypatch.setenv("AQUATRACK_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("AQUATRACK_LLM_TIMEOUT_S", "7")
    real = explain.explainer_from_env()  # builds a client; makes no request
    assert (
        isinstance(real, OpenAIExplainer)
        and real._client.timeout == 7
        and real._client.max_retries == 1
    )


@pytest.mark.parametrize(
    "handler,message",
    [
        (answering(api_response("not json at all")), "not JSON"),
        (
            answering(
                api_response(
                    '{"summary": "cut', status="incomplete", incomplete="max_output_tokens"
                )
            ),
            "incomplete: max_output_tokens",
        ),
        (answering(api_response(refusal="I can't help with that.")), "refused"),
        (
            answering(
                {"error": {"message": "bad key", "type": "invalid_request_error"}}, status_code=401
            ),
            "API error 401",
        ),
        (answering({"error": {"message": "slow down"}}, status_code=429), "rate limited"),
        (answering({"error": {"message": "boom"}}, status_code=500), "API error 500"),
    ],
)
def test_bad_answers_and_api_errors_become_one_plain_error(handler, message, caplog):
    with caplog.at_level(logging.DEBUG), pytest.raises(ExplainError, match=message) as e:
        explainer(handler).complete("x", "s", {"type": "object"}, {})
    assert SECRET not in str(e.value) and SECRET not in caplog.text


def test_a_timeout_and_a_dropped_connection_are_reported_not_raised_raw():
    def slow(request):
        raise httpx2.ReadTimeout("too slow", request=request)

    def down(request):
        raise httpx2.ConnectError("no route", request=request)

    with pytest.raises(ExplainError, match="timed out"):
        explainer(slow).complete("x", "s", {"type": "object"}, {})
    with pytest.raises(ExplainError, match="network error"):
        explainer(down).complete("x", "s", {"type": "object"}, {})


def test_rewording_is_off_by_default_and_needs_both_the_provider_and_a_key(monkeypatch, caplog):
    assert explain.explainer_from_env() is None  # nothing set
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    assert explain.explainer_from_env() is None  # a key alone switches nothing on
    monkeypatch.setenv("AQUATRACK_LLM", "claude")
    assert explain.explainer_from_env() is None  # the old Anthropic switch does nothing now
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("AQUATRACK_LLM_PROVIDER", "openai")
    with caplog.at_level(logging.WARNING):
        assert explain.explainer_from_env() is None  # provider without a key: still off
    monkeypatch.setenv("AQUATRACK_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    assert explain.explainer_from_env() is None  # no other provider exists
    assert SECRET not in caplog.text


def test_the_anthropic_sdk_is_no_longer_a_dependency():
    project = open("pyproject.toml").read()
    assert "anthropic" not in project and 'llm = ["openai' in project
    assert "anthropic" not in open("uv.lock").read()


# ---------- what is sent ----------


def test_the_plan_payload_holds_structure_only_never_identifiers_or_the_swimmers_words():
    plan = week(ctx=SUPPORTED)
    plan.id, plan.sessions[0].id = "plan-secret-id", "session-secret-id"
    plan.sessions[0].completion = None
    plan.sessions[0].items.append(
        training.PlanItem(
            name="My private activity name", category="custom", minutes=5, source="manual"
        )
    )
    sent = json.dumps(build_plan_payload(plan))
    for forbidden in (
        "vid-a",
        "a1",
        UID,
        "plan-secret-id",
        "session-secret-id",
        "My private activity name",
        "cp.recurs.x",
        "@",
    ):
        assert forbidden not in sent
    payload = build_plan_payload(plan)
    assert set(payload) == {"plan", "sessions", "recommendations"}
    assert [s["id"] for s in payload["sessions"]] == ["s1", "s2", "s3"]
    assert payload["plan"]["basis"] == "analysis_based"


# ---------- the plan validator (answers are mocked) ----------


class Mock:
    model = "mock-model"

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def complete(self, name, system, schema, payload):
        self.calls.append((name, payload))
        if self.error:
            raise self.error
        return self.answer(payload) if callable(self.answer) else self.answer


def good(payload, **over):
    """A well-behaved model: says the same thing, shorter. MOCKED."""
    sessions = [
        {
            "id": s["id"],
            "text": f"{s['title']}: about {s['minutes']} minutes, starting with {s['activities'][0]['name'].lower()}.",
        }
        for s in payload["sessions"]
    ]
    return {
        "summary": "A week of unhurried practice that you can change as you like.",
        "sessions": sessions,
        **over,
    }


def test_a_faithful_rewording_is_accepted_and_changes_no_activity_or_duration():
    plan = week()
    before = plan.model_dump(exclude=KEEP)
    mock = Mock(good)
    out = explain_plan(plan, mock)
    assert out.explanation.source == "llm" and out.explanation.model == "mock-model"
    assert out.explained and all(s.explained for s in out.sessions)
    assert out.model_dump(exclude=KEEP) == before
    assert mock.calls[0][0] == "plan_rewording" and len(mock.calls) == 1


def bad_session(text):
    return lambda p: good(p, sessions=[{"id": "s1", "text": text}])


@pytest.mark.parametrize(
    "answer,reason",
    [
        ("just a string", "not the requested structure"),
        ({"summary": "ok"}, "not the requested structure"),
        (
            lambda p: good(p, sessions=[{"id": "s9", "text": "An extra session."}]),
            "unknown session id",
        ),
        (lambda p: good(p, sessions=[{"id": "s1", "text": "Fine."}] * 2), "answered twice"),
        (lambda p: good(p, sessions=[{"id": "s1"}]), "malformed entry"),
        (bad_session("x" * 601), "over 600 characters"),
        (bad_session("Swim for 90 minutes today."), "numbers not in the plan"),
        (bad_session("Do 20 x 100 m steady."), "numbers not in the plan"),
        (bad_session("Finish with some sculling and a pull buoy set."), "not in the plan"),
        (bad_session("Add a few sprints at the end."), "not in the plan"),
        (bad_session("Start with Regular breathing rhythm."), "not in this part of the plan"),
        (bad_session("Research shows this is the best way to train."), "mentions research"),
        (
            bad_session("As Wulf (2013) found, focus matters."),
            "cites a source|numbers not in the plan",
        ),
        (bad_session("This will improve your times."), "never allowed|promise"),
        (bad_session("You will swim faster after this week."), "promise"),
        (bad_session("Try to take fewer breaths each length."), "unsafe"),
        (bad_session("Hold your breath for the last few strokes."), "never allowed"),
        (bad_session("Go all-out on the final repeat."), "not in the plan|unsafe"),
        (bad_session("This helps prevent shoulder injury."), "never allowed"),
        (
            bad_session("Your stroke is uneven, so count carefully."),
            "worded as a finding about the swimmer",
        ),
        (bad_session("We noticed your rhythm drops off."), "worded as a finding about the swimmer"),
        (
            bad_session("This fixes your weakness in the water."),
            "confirmed fault|finding about the swimmer",
        ),
        (
            lambda p: good(
                p, summary="Your video showed an uneven rhythm, so this week targets it."
            ),
            "finding about the swimmer",
        ),
        (lambda p: good(p, summary=""), "empty"),
    ],
)
def test_anything_the_plan_does_not_contain_rejects_the_whole_answer(answer, reason):
    plan = week(ctx=NO_ISSUE)  # goal-based: nothing was found in this swimmer's swimming
    with pytest.raises(Rejected, match=reason):
        validate_plan(plan, answer(build_plan_payload(plan)) if callable(answer) else answer)
    before = plan.model_dump(exclude={"explanation"})
    out = explain_plan(plan, Mock(answer))
    assert out.explanation.source == "template" and "rejected" in out.explanation.note
    assert out.explained == "" and all(s.explained == "" for s in out.sessions)
    assert out.model_dump(exclude={"explanation"}) == before  # the plan itself is untouched


def test_an_analysis_based_plan_may_refer_to_the_finding_but_never_as_a_confirmed_fault():
    plan = week(ctx=SUPPORTED)
    ok = good(
        build_plan_payload(plan),
        summary="Your analysis found something worth a look, so this week starts there.",
    )
    assert validate_plan(plan, ok)[0].startswith("Your analysis")
    with pytest.raises(Rejected, match="confirmed fault"):
        validate_plan(
            plan,
            good(build_plan_payload(plan), summary="This is definitely a fault in your stroke."),
        )


@pytest.mark.parametrize(
    "error",
    [
        ExplainError("timed out"),
        ExplainError("refused"),
        ValueError("bad json"),
        RuntimeError("anything"),
    ],
)
def test_when_the_model_fails_the_plan_is_shown_exactly_as_the_planner_wrote_it(error):
    plan = week()
    before = plan.model_dump(exclude={"explanation"})
    out = explain_plan(plan, Mock(error=error))
    assert out.explanation.source == "template" and "unavailable" in out.explanation.note
    assert out.model_dump(exclude={"explanation"}) == before and out.summary


def test_no_explainer_means_no_call_and_the_plan_is_complete():
    plan = explain_plan(week(), None)
    assert plan.explanation.source == "template" and plan.summary and plan.sessions[0].items


def test_the_real_adapter_end_to_end_with_a_mocked_answer_and_with_a_lying_one():
    plan = week()
    truthful = json.dumps(good(build_plan_payload(plan)))
    out = explain_plan(week(), explainer(answering(api_response(truthful))))
    assert out.explanation.source == "llm" and out.explanation.model == "gpt-6-luna"
    lie = json.dumps(
        good(build_plan_payload(plan), summary="Studies prove this plan will improve your stroke.")
    )
    out = explain_plan(week(), explainer(answering(api_response(lie))))
    assert out.explanation.source == "template" and out.explained == ""


# ---------- saving with and without a model, and the HTTP API ----------


@pytest.fixture
def store():
    s = MemoryStore()
    s.profiles[UID] = profile()
    s.profiles["swimmer-2"] = profile()
    return s


def test_a_saved_plan_keeps_validated_wording_and_drops_rejected_wording(store):
    saved = training.save_plan(store, UID, "week", MON, explainer=Mock(good))["plan"]
    assert saved["explanation"]["source"] == "llm" and saved["explained"]
    assert all(store.get_doc("training_sessions", s["id"])["explained"] for s in saved["sessions"])
    liar = Mock(lambda p: good(p, summary="Do 500 push-ups."))
    again = training.save_plan(store, UID, "week", date(2026, 11, 23), explainer=liar)["plan"]
    assert again["explanation"]["source"] == "template" and again["explained"] == ""
    assert len(again["sessions"]) == 3 and again["summary"]  # saved and usable all the same


GOOD = {"Authorization": "Bearer good-token"}
THEIRS = {"Authorization": "Bearer other-token"}


@pytest.fixture
def client(monkeypatch, store):
    def fake_verify(token: str) -> dict:
        if token == "good-token":
            return {"uid": UID, "email": "alice@example.com"}
        if token == "other-token":
            return {"uid": "swimmer-2"}
        raise auth.InvalidIdTokenError("bad token")

    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    main.app.dependency_overrides[main.get_runner] = lambda: InlineRunner(store, None)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


ROUTES = [
    ("get", "/training?today=2026-11-16", None),
    ("post", "/training/plans/preview", {"kind": "week", "start": "2026-11-16"}),
    ("post", "/training/plans", {"kind": "week", "start": "2026-11-16"}),
    ("get", "/training/calendar?start=2026-11-01&end=2026-11-30", None),
    ("post", "/training/sessions", {"date": "2026-11-16", "title": "x", "items": []}),
    ("patch", "/training/sessions/abc", {"title": "x"}),
    ("post", "/training/sessions/abc/complete", {"completed_on": "2026-11-16"}),
    ("delete", "/training/sessions/abc", None),
]


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_every_training_route_needs_a_login(client, method, path, body):
    kw = {"json": body} if body is not None else {}
    assert getattr(client, method)(path, **kw).status_code == 401
    assert (
        getattr(client, method)(path, headers={"Authorization": "Bearer nope"}, **kw).status_code
        == 401
    )


def test_the_whole_journey_over_http_with_no_model_and_no_key_in_any_answer(
    client, store, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)  # present but the provider is not switched on
    add_video(store, supported=False)
    answers = []

    def call(method, path, **kw):
        res = getattr(client, method)(path, headers=GOOD, **kw)
        answers.append(res.text)
        return res

    over = call("get", "/training?today=2026-11-16").json()
    assert over["llm_enabled"] is False and over["analysis"]["state"] == "no_supported_issue"
    assert over["recommendations"] and all(
        r["basis"] == "goal_based" for r in over["recommendations"]
    )
    preview = call(
        "post", "/training/plans/preview", json={"kind": "week", "start": "2026-11-16"}
    ).json()
    assert preview["status"] == "preview" and not store.docs["training_plans"]
    saved = call("post", "/training/plans", json={"kind": "week", "start": "2026-11-16"}).json()
    assert saved["saved"] and saved["plan"]["explanation"]["source"] == "template"
    first = saved["plan"]["sessions"][0]["id"]
    again = call("post", "/training/plans", json={"kind": "week", "start": "2026-11-16"}).json()
    assert again["saved"] is False and again["conflict"]["kind"] == "week_overlap"
    moved = call(
        "patch", f"/training/sessions/{first}", json={"date": "2026-11-17", "time": "07:15"}
    )
    assert moved.status_code == 200 and moved.json()["date"] == "2026-11-17"
    done = call(
        "post",
        f"/training/sessions/{first}/complete",
        json={"completed_on": "2026-11-17", "note": "ok", "video_id": "vid-a"},
    )
    assert done.json()["status"] == "completed" and done.json()["linked_video_id"] == "vid-a"
    made = call(
        "post",
        "/training/sessions",
        json={
            "date": "2026-11-19",
            "title": "Own swim",
            "items": [{"activity_id": "", "name": "Laps", "minutes": 20}],
        },
    )
    assert made.status_code == 201 and made.json()["origin"] == "manual"
    cal = call("get", "/training/calendar?start=2026-11-16&end=2026-11-22").json()
    assert [s["date"] for s in cal["sessions"]] == [
        "2026-11-17",
        "2026-11-18",
        "2026-11-19",
        "2026-11-21",
    ]
    assert cal["videos"][0]["id"] == "vid-a"
    assert call("delete", f"/training/sessions/{made.json()['id']}").json()["deleted"]
    bad = call("patch", f"/training/sessions/{first}", json={"date": "tomorrow"})
    assert bad.status_code == 422 and "YYYY-MM-DD" in bad.json()["detail"]
    assert call("get", "/training?today=yesterday").status_code == 422
    assert all(SECRET not in a and "OPENAI" not in a for a in answers)

    # someone else sees none of it and can change none of it
    assert client.get("/training?today=2026-11-16", headers=THEIRS).json()["plans"] == []
    assert (
        client.get("/training/calendar?start=2026-11-16&end=2026-11-22", headers=THEIRS).json()[
            "sessions"
        ]
        == []
    )
    for res in (
        client.patch(f"/training/sessions/{first}", headers=THEIRS, json={"title": "Mine"}),
        client.post(
            f"/training/sessions/{first}/complete",
            headers=THEIRS,
            json={"completed_on": "2026-11-17"},
        ),
        client.delete(f"/training/sessions/{first}", headers=THEIRS),
    ):
        assert res.status_code == 404 and res.json()["detail"] == "Session not found."
    assert (
        client.post(
            f"/training/sessions/{first}/complete",
            headers=THEIRS,
            json={"completed_on": "2026-11-17"},
        ).status_code
        == 404
    )
    assert store.get_doc("training_sessions", first)["status"] == "completed"
