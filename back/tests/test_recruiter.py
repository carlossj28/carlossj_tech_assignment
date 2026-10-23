"""Recruiter panel endpoints against a real Postgres. Skipped without DATABASE_URL."""
import os
from uuid import uuid4

import pytest

os.environ.setdefault("SESSION_SECRET", "test-secret")

import auth  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs Postgres (docker compose up -d)"
)


@pytest.fixture(scope="module")
def api():
    from fastapi.testclient import TestClient

    import db
    from main import app
    db.init_db()
    client = TestClient(app)
    client.cookies.set("session", auth.issue_session("demo"))
    return client


def _conversation(minutes_quiet: int, completed: bool = False) -> str:
    import db
    cid = db.start_conversation("chat", "¡Hola!")
    with db.pool().connection() as conn:
        conn.execute(
            "UPDATE conversations SET completed = %s, "
            "last_activity_at = now() - make_interval(mins => %s) WHERE id = %s",
            (completed, minutes_quiet, cid))
    return cid


def test_requires_login():
    from fastapi.testclient import TestClient

    from main import app
    assert TestClient(app).get("/api/recruiter/conversations").status_code == 401


def test_list_newest_first_with_inactive_derived(api):
    quiet, closed, fresh = _conversation(45), _conversation(45, completed=True), _conversation(0)
    rows = {r["id"]: r for r in api.get("/api/recruiter/conversations").json()}
    assert rows[quiet]["inactive"] is True
    assert rows[closed]["inactive"] is False            # a closed interview is never inactive
    assert rows[fresh]["inactive"] is False
    ids = [r["id"] for r in api.get("/api/recruiter/conversations").json()]
    assert ids.index(fresh) < ids.index(quiet)          # by last activity, newest first


def test_list_carries_the_city_for_the_analytics(api):
    import db
    cid, blank = _conversation(0), _conversation(0)
    with db.pool().connection() as conn:
        conn.execute("""UPDATE conversations SET extracted_fields = '{"city": "Madrid"}' WHERE id = %s""", (cid,))
    rows = {r["id"]: r for r in api.get("/api/recruiter/conversations").json()}
    assert rows[cid]["city"] == "Madrid"
    assert rows[blank]["city"] is None                  # no city yet


def test_detail_has_data_and_text_turns(api):
    cid = _conversation(0)
    body = api.get(f"/api/recruiter/conversations/{cid}").json()
    assert body["extracted_fields"] == {} and body["summary"] is None
    assert body["sentiment"] is None
    assert [(t["role"], t["content"]) for t in body["turns"]] == [("assistant", "¡Hola!")]
    assert "tool_calls" not in body["turns"][0]


def test_detail_unknown_id(api):
    assert api.get(f"/api/recruiter/conversations/{uuid4()}").status_code == 404
