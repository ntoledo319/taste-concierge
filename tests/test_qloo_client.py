"""Qloo client: URL/param building, auth header, error paths, offline mode."""

from __future__ import annotations

import urllib.parse

import pytest

from taste_concierge.qloo_client import (
    DEFAULT_BASE_URL,
    OfflineQlooClient,
    QlooClient,
    QlooError,
    extract_entities,
    make_client,
)


def recording_transport(payload):
    """Capture (url, headers) and return a canned payload."""
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        return payload

    transport.calls = calls
    return transport


def test_insights_builds_query_params():
    transport = recording_transport({"results": {"entities": []}})
    client = QlooClient("test-key", transport=transport)
    client.insights(
        "urn:entity:movie",
        signal_entities=["AAA", "BBB"],
        signal_tags=["T1"],
        limit=7,
    )
    url, headers = transport.calls[0]
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    assert url.startswith(f"{DEFAULT_BASE_URL}/v2/insights?")
    assert params["filter.type"] == ["urn:entity:movie"]
    assert params["signal.interests.entities"] == ["AAA,BBB"]
    assert params["signal.interests.tags"] == ["T1"]
    assert params["take"] == ["7"]
    assert headers == {"X-Api-Key": "test-key"}


def test_search_builds_query_params():
    transport = recording_transport({"results": []})
    client = QlooClient("test-key", transport=transport)
    client.search_entities("blade runner", types=["urn:entity:movie"])
    url, headers = transport.calls[0]
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert urllib.parse.urlparse(url).path == "/search"
    assert params["query"] == ["blade runner"]
    assert params["types"] == ["urn:entity:movie"]
    assert headers["X-Api-Key"] == "test-key"


def test_base_url_override():
    transport = recording_transport({"results": []})
    client = QlooClient("k", base_url="http://127.0.0.1:9999", transport=transport)
    client.search_entities("dune")
    assert transport.calls[0][0].startswith("http://127.0.0.1:9999/search?")


def test_constructor_rejects_empty_key():
    with pytest.raises(QlooError, match="QLOO_API_KEY"):
        QlooClient("")


def test_from_env_requires_key():
    with pytest.raises(QlooError, match="QLOO_API_KEY"):
        QlooClient.from_env()


def test_from_env_reads_key_and_base_url(monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "env-key")
    monkeypatch.setenv("QLOO_BASE_URL", "http://example.test")
    client = QlooClient.from_env()
    assert client.api_key == "env-key"
    assert client.base_url == "http://example.test"


def test_insights_rejects_bad_filter_type():
    client = QlooClient("k", transport=recording_transport({}))
    with pytest.raises(QlooError, match="urn:entity"):
        client.insights("movie")


def test_http_error_wrapped_as_qloo_error(monkeypatch):
    import io
    import urllib.error

    from taste_concierge import qloo_client

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key")
        )

    monkeypatch.setattr(qloo_client.urllib.request, "urlopen", fake_urlopen)
    client = QlooClient("k")
    with pytest.raises(QlooError, match="HTTP 401"):
        client.search_entities("dune")


def test_extract_entities_handles_both_shapes():
    search_shape = {"results": [{"id": "S1", "name": "A"}]}
    insights_shape = {"results": {"entities": [{"entity_id": "I1", "name": "B"}]}}
    assert extract_entities(search_shape)[0].id == "S1"
    assert extract_entities(insights_shape)[0].id == "I1"
    assert extract_entities({}) == []


def test_make_client_offline_by_default_without_key():
    client = make_client()
    assert client.offline is True


def test_make_client_live_with_key(monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "real-key")
    client = make_client()
    assert client.offline is False


def test_make_client_offline_flag_wins_over_key(monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "real-key")
    monkeypatch.setenv("QLOO_OFFLINE", "1")
    assert make_client().offline is True


# -- offline fixture client ---------------------------------------------------

def test_offline_search_resolves_and_labels_fixture(offline_client):
    results = offline_client.search_entities("Inception", types=["urn:entity:movie"])
    assert len(results) == 1
    assert results[0].name == "Inception"
    assert results[0].id
    assert results[0].source == "fixture"
    assert "sci-fi" in results[0].tags


def test_offline_search_unknown_returns_empty_not_invented(offline_client):
    assert offline_client.search_entities("Definitely Not A Real Thing") == []


def test_offline_insights_per_category(offline_client):
    movies = offline_client.insights("urn:entity:movie", signal_entities=["X"])
    assert movies and all(e.source == "fixture" for e in movies)
    assert movies[0].name == "Blade Runner 2049"
    with pytest.raises(QlooError, match="no offline insights fixture"):
        offline_client.insights("urn:entity:podcast")


def test_offline_insights_respects_limit(offline_client):
    results = offline_client.insights("urn:entity:movie", limit=2)
    assert len(results) == 2


def test_offline_tags_filter(offline_client):
    tags = offline_client.tags(query="sci")
    assert tags and all("sci" in t.name.lower() for t in tags)
    assert len(offline_client.tags()) >= 9
