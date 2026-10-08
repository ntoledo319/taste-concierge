"""Web simulator: page serves, state endpoint works, messages flow."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from taste_concierge.agent import TasteConciergeAgent, TemplatePhraser
from taste_concierge.qloo_client import OfflineQlooClient
from taste_concierge.web import make_handler


@pytest.fixture
def server():
    agent = TasteConciergeAgent(OfflineQlooClient(), phraser=TemplatePhraser())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(agent))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def _post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_index_serves_dark_chat_page(server):
    status, body = _get(server + "/")
    assert status == 200
    assert "taste-concierge" in body
    assert "color-scheme: dark" in body


def test_state_endpoint_reports_offline_mode(server):
    status, payload = _get(server + "/api/state")
    data = json.loads(payload)
    assert status == 200
    assert "OFFLINE" in data["mode"]
    assert "greeting" in data


def test_message_flow_updates_plan_and_trail(server):
    _, reply = _post(server + "/api/message", {"message": "movies: Inception"})
    assert "Inception" in reply["reply"]
    _, reply = _post(server + "/api/message", {"message": "plan my evening"})
    assert reply["plan"][0]["name"] == "Blade Runner 2049"
    assert reply["plan"][0]["source"] == "fixture"
    endpoints = {c["endpoint"] for c in reply["trail"]}
    assert "/search" in endpoints and "/v2/insights" in endpoints


def test_404_for_unknown_path(server):
    import urllib.error

    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server + "/nope")
    assert exc.value.code == 404
