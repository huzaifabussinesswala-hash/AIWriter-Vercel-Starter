from datetime import datetime, timedelta, timezone

import pytest
import requests

from aiwriter import ai_provider, options, repo
from aiwriter.ai_provider import ProviderError
from aiwriter.config import load_settings
from aiwriter.usage import build_usage, compute_usage, period_bounds

from conftest import EMAIL, PASSWORD, login, post, register_and_login, signup, user_id_for, verify

VALID = {"prompt": "Announce our spring sale", "writing_type": "email", "output_language": "english",
         "tone": "friendly", "length": "short"}


def count_rows(database):
    with database.connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM generations").scalar()


def fill_today(database, user_id, how_many, when=None):
    when = when or datetime.now(timezone.utc)
    with database.connection() as conn:
        for _ in range(how_many):
            repo.insert_generation(conn, user_id, "general", "p", "english", "formal", "short", "t", when)


# ----------------------------------------------------------- route behaviour


def test_dashboard_shows_every_option(logged_in):
    html = logged_in.get("/dashboard").get_data(as_text=True)
    for label in [label for _, label, *_ in options.WRITING_TYPES] + [l for _, l, *_ in options.LANGUAGES] \
            + [l for _, l in options.TONES] + [l for _, l, *_ in options.LENGTHS]:
        assert f">{label}</option>" in html, label
    assert 'id="generate-form"' in html and 'maxlength="2000"' in html


def test_successful_generation_is_saved_for_the_user_and_shown(logged_in, ai, app_db):
    response = post(logged_in, "/generate", VALID)
    assert response.status_code == 302 and "/dashboard?view=" in response.headers["Location"]
    assert ai.calls == [{"prompt": VALID["prompt"], "writing_type": "email", "output_language": "english",
                         "tone": "friendly", "length": "short"}]
    page = logged_in.get(response.headers["Location"]).get_data(as_text=True)
    assert "Here is your generated text." in page and 'id="copy-btn"' in page and "Generate again" in page
    with app_db.connection() as conn:
        rows = conn.execute("SELECT * FROM generations").fetchall()
    assert len(rows) == 1 and rows[0]["user_id"] == user_id_for(app_db)
    assert rows[0]["generated_text"] == "Here is your generated text."


def test_missing_prompt_is_rejected_without_calling_the_provider(logged_in, ai, app_db):
    response = post(logged_in, "/generate", dict(VALID, prompt="   "))
    assert response.status_code == 400
    assert "Please describe what you want written." in response.get_data(as_text=True)
    assert ai.calls == [] and count_rows(app_db) == 0


def test_overlong_prompt_is_rejected(logged_in, ai):
    response = post(logged_in, "/generate", dict(VALID, prompt="x" * (options.MAX_PROMPT_CHARS + 1)))
    assert response.status_code == 400 and "too long" in response.get_data(as_text=True)
    assert ai.calls == []


@pytest.mark.parametrize("field", ["writing_type", "output_language", "tone", "length"])
def test_invalid_options_are_rejected_server_side(logged_in, ai, field):
    response = post(logged_in, "/generate", dict(VALID, **{field: "hacked"}))
    assert response.status_code == 400 and "Please choose one of the listed options." in response.get_data(as_text=True)
    assert ai.calls == []


def test_provider_failure_keeps_input_saves_nothing_and_shows_message(logged_in, ai, app_db):
    ai.error = ProviderError("timeout", "The AI service took too long to respond. Please try again.", 504)
    response = post(logged_in, "/generate", dict(VALID, tone="creative", length="long"))
    html = response.get_data(as_text=True)
    assert response.status_code == 504
    assert "took too long" in html
    assert "Announce our spring sale" in html  # prompt preserved
    assert '<option value="creative" selected>' in html and '<option value="long" selected>' in html
    assert count_rows(app_db) == 0
    # the failure did not count against the quota
    ai.error = None
    assert post(logged_in, "/generate", VALID).status_code == 302


def test_ai_output_is_escaped_not_trusted_as_html(logged_in, ai):
    ai.text = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    location = post(logged_in, "/generate", VALID).headers["Location"]
    html = logged_in.get(location).get_data(as_text=True)
    assert "<script>alert" not in html and "&lt;script&gt;" in html and "<img src=x" not in html


def test_history_lists_generations_and_is_private(logged_in, ai, app_db, mailbox):
    location = post(logged_in, "/generate", VALID).headers["Location"]
    assert "Announce our spring sale" in logged_in.get("/history").get_data(as_text=True)

    stranger = logged_in.application.test_client()
    register_and_login(stranger, mailbox, email="other@example.com")
    assert "Announce our spring sale" not in stranger.get("/history").get_data(as_text=True)
    page = stranger.get(location).get_data(as_text=True)  # someone else's generation id
    assert "Here is your generated text." not in page and "could not be found" in page


def test_dashboard_shows_recent_generations_and_usage(logged_in, ai):
    for i in range(3):
        post(logged_in, "/generate", dict(VALID, prompt=f"Prompt number {i}"))
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "Prompt number 2" in html and "Recent generations" in html
    assert "3 / 5" in html and "2 left" in html and "3 / 150" in html


# ----------------------------------------------------------- limits


def test_free_daily_limit_blocks_before_calling_the_provider(logged_in, ai, app_db):
    fill_today(app_db, user_id_for(app_db), 5)
    response = post(logged_in, "/generate", VALID)
    assert response.status_code == 429 and "daily limit" in response.get_data(as_text=True)
    assert ai.calls == [] and count_rows(app_db) == 5


def test_free_monthly_limit_blocks(logged_in, ai, app_db):
    uid = user_id_for(app_db)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fill_today(app_db, uid, 150, when=month_start)  # earlier in the month, none today (unless today is the 1st)
    if month_start.date() == now.date():
        pytest.skip("today is the 1st: cannot separate daily from monthly usage")
    response = post(logged_in, "/generate", VALID)
    assert response.status_code == 429 and "monthly limit" in response.get_data(as_text=True)
    assert ai.calls == []


def test_pro_plan_has_no_daily_limit_but_has_monthly_limit(logged_in, ai, app_db):
    uid = user_id_for(app_db)
    with app_db.connection() as conn:
        conn.execute("UPDATE users SET plan = ? WHERE id = ?", ("pro", uid))
    fill_today(app_db, uid, 12)
    assert post(logged_in, "/generate", VALID).status_code == 302
    html = logged_in.get("/dashboard").get_data(as_text=True)
    assert "no daily limit" in html and "/ 500" in html


def test_limit_is_rechecked_after_the_ai_call_to_stop_concurrent_bypass(logged_in, ai, app_db):
    uid = user_id_for(app_db)
    fill_today(app_db, uid, 4)
    # While this request waits on the AI, other requests use up the last slot.
    ai.side_effect = lambda: fill_today(app_db, uid, 1)
    response = post(logged_in, "/generate", VALID)
    assert response.status_code == 429
    assert count_rows(app_db) == 5  # the late result was discarded, quota not exceeded


def test_period_bounds_and_midnight_boundaries(app_db):
    now = datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
    day_start, day_end, month_start, month_end = period_bounds(now)
    assert day_start == datetime(2026, 12, 31, tzinfo=timezone.utc)
    assert day_end == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert month_start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert month_end == datetime(2027, 1, 1, tzinfo=timezone.utc)

    with app_db.connection() as conn:
        uid = repo.create_user(conn, "Ann", "ann@example.com", "h", now)
        user = repo.get_user_by_id(conn, uid)
        repo.insert_generation(conn, uid, "general", "a", "english", "formal", "short", "t", datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc))
        repo.insert_generation(conn, uid, "general", "b", "english", "formal", "short", "t", datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        repo.insert_generation(conn, uid, "general", "c", "english", "formal", "short", "t", datetime(2026, 11, 30, 23, 59, 59, tzinfo=timezone.utc))
        before = compute_usage(conn, user, now)
        after = compute_usage(conn, user, datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
    assert (before.daily_used, before.monthly_used) == (1, 1)
    assert (after.daily_used, after.monthly_used) == (1, 1)


def test_remaining_quota_never_goes_negative_and_percent_is_capped():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    usage = build_usage("free", daily_used=9, monthly_used=200, now=now)
    assert usage.daily_remaining == 0 and usage.monthly_remaining == 0
    assert usage.daily_percent == 100 and usage.monthly_percent == 100
    assert usage.blocked_reason == "daily" and not usage.allowed
    pro = build_usage("pro", daily_used=900, monthly_used=100, now=now)
    assert pro.daily_limit is None and pro.daily_remaining is None and pro.allowed
    business = build_usage("business", 0, 1999, now)
    assert business.monthly_limit == 2000 and business.monthly_remaining == 1 and business.allowed
    assert build_usage("business", 0, 2000, now).blocked_reason == "monthly"
    assert build_usage("unknown-plan", 0, 0, now).plan == "free"


def test_users_cannot_pick_their_own_plan(logged_in, app_db):
    for path in ("/plans", "/account/profile"):
        post(logged_in, path, {"plan": "business", "name": "Test Writer"})
    with app_db.connection() as conn:
        assert repo.get_user_by_email(conn, EMAIL)["plan"] == "free"
    html = logged_in.get("/plans").get_data(as_text=True)
    assert "Upgrade unavailable" in html and "Payments are not enabled yet" in html


# ----------------------------------------------------------- provider unit tests


class FakeResponse:
    def __init__(self, status=200, payload=None, json_error=False):
        self.status_code = status
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


@pytest.fixture
def provider_settings(env):
    return load_settings(env)


def ok_payload(text="Hello world"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def call(settings):
    return ai_provider.generate_text(settings, "Write hello", "email", "urdu", "formal", "short")


def test_provider_success_sends_authorization_timeout_and_structured_prompt(monkeypatch, provider_settings):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None, allow_redirects=None):
        seen.update(url=url, json=json, headers=headers, timeout=timeout, redirects=allow_redirects)
        return FakeResponse(200, ok_payload("  Salaam!  "))

    monkeypatch.setattr(requests, "post", fake_post)
    assert call(provider_settings) == "Salaam!"
    assert seen["url"] == "https://ai.test.invalid/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer test-ai-key-123456"
    assert seen["timeout"] == (5.0, 30.0) and seen["redirects"] is False
    system, user = seen["json"]["messages"]
    assert seen["json"]["model"] == "test-model" and seen["json"]["max_tokens"] == 400
    assert "Urdu" in system["content"] and "Formal" in system["content"] and "email" in system["content"].lower()
    assert "Write hello" in user["content"]


def test_url_normalisation():
    assert ai_provider.chat_completions_url("https://x.test/v1") == "https://x.test/v1/chat/completions"
    assert ai_provider.chat_completions_url("https://x.test/v1/chat/completions/") == "https://x.test/v1/chat/completions"


@pytest.mark.parametrize("raised, kind, status", [
    (requests.Timeout("slow"), "timeout", 504),
    (requests.ConnectionError("down"), "unavailable", 503),
    (requests.RequestException("odd"), "request_failed", 502),
])
def test_provider_network_errors_are_mapped(monkeypatch, provider_settings, raised, kind, status):
    def fake_post(*args, **kwargs):
        raise raised

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(ProviderError) as info:
        call(provider_settings)
    assert (info.value.kind, info.value.http_status) == (kind, status)


@pytest.mark.parametrize("response, kind, status", [
    (FakeResponse(429), "rate_limited", 429),
    (FakeResponse(401), "auth", 503),
    (FakeResponse(403), "auth", 503),
    (FakeResponse(500), "server_error", 502),
    (FakeResponse(302), "http_error", 502),
    (FakeResponse(400), "http_error", 502),
    (FakeResponse(200, json_error=True), "invalid_response", 502),
    (FakeResponse(200, {"unexpected": True}), "invalid_response", 502),
    (FakeResponse(200, {"choices": []}), "invalid_response", 502),
    (FakeResponse(200, ok_payload("   ")), "empty", 502),
    (FakeResponse(200, ok_payload(None)), "empty", 502),
])
def test_provider_http_and_content_errors_are_mapped(monkeypatch, provider_settings, response, kind, status):
    monkeypatch.setattr(requests, "post", lambda *a, **k: response)
    with pytest.raises(ProviderError) as info:
        call(provider_settings)
    assert (info.value.kind, info.value.http_status) == (kind, status)
    assert provider_settings.ai_api_key not in info.value.user_message


def test_unconfigured_provider_gives_a_clear_error(env):
    settings = load_settings(dict(env, AI_API_URL="", AI_MODEL=""))
    with pytest.raises(ProviderError) as info:
        call(settings)
    assert info.value.kind == "not_configured" and info.value.http_status == 503


def test_provider_error_never_leaks_key_or_traceback_through_the_page(logged_in, monkeypatch, app_db):
    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("HTTPSConnectionPool(host='ai.test.invalid') Authorization: Bearer test-ai-key-123456")

    monkeypatch.setattr(requests, "post", fake_post)
    response = post(logged_in, "/generate", VALID)
    html = response.get_data(as_text=True)
    assert response.status_code == 503 and "unreachable" in html
    assert "test-ai-key-123456" not in html and "Traceback" not in html and "HTTPSConnectionPool" not in html
    assert count_rows(app_db) == 0


def test_unexpected_exception_shows_generic_error_page(logged_in, ai):
    def explode():
        raise RuntimeError("secret internal detail")

    ai.side_effect = explode
    response = post(logged_in, "/generate", VALID)
    html = response.get_data(as_text=True)
    assert response.status_code == 500 and "secret internal detail" not in html and "Traceback" not in html
