"""Stdlib ``urllib`` client for the Qloo hackathon API.

    QlooClient.from_env()                      # live API (needs QLOO_API_KEY)
    OfflineQlooClient()                        # recorded fixtures, zero network
    make_client(prefer_offline=None)           # picks one, always labeled

API facts (from the hackathon developer guide):

- Base URL is ``https://hackathon.api.qloo.com`` — hackathon keys ONLY work
  there (override with ``QLOO_BASE_URL`` for testing).
- Auth is the ``X-Api-Key`` header — NOT Bearer, NOT a query param.
- ``GET /v2/insights`` with ``filter.type`` (e.g. ``urn:entity:movie``) and
  optional signals ``signal.interests.entities`` / ``signal.interests.tags``
  (comma-separated ids). GET, not POST; everything in the query string.
- ``GET /search?query=<name>&types=...`` resolves names to Qloo entity ids.
- ``GET /v2/tags`` lists valid tag ids.
- ``/recs`` and ``/recommendations`` are legacy and intentionally NOT used.

Responses are verbose JSON with inconsistent id fields across endpoints
(``id`` on /search, ``entity_id`` on /v2/insights); :func:`extract_entities`
normalizes both into :class:`Entity`. Offline mode serves hand-recorded
fixtures from ``taste_concierge/fixtures/`` and every entity it returns is
labeled so the UI can say so.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# filter.type -> short fixture name, for insights fixtures.
_INSIGHTS_FIXTURES = {
    "urn:entity:movie": "insights_movie.json",
    "urn:entity:place": "insights_place.json",
    "urn:entity:artist": "insights_artist.json",
    "urn:entity:book": "insights_book.json",
}


class QlooError(Exception):
    """Raised for configuration, transport, or Qloo API failures."""


@dataclass
class Entity:
    """A normalized Qloo entity, wherever it came from."""

    id: str
    name: str
    description: str = ""
    entity_type: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "live"  # "live" | "fixture"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def extract_entities(payload: dict[str, Any], source: str = "live") -> list[Entity]:
    """Pull entities out of Qloo's verbose JSON, tolerating both shapes:
    ``{"results": [...]}`` (search) and ``{"results": {"entities": [...]}}``
    (insights). Missing fields degrade to empty strings, never exceptions."""
    results = payload.get("results", [])
    if isinstance(results, dict):
        items = results.get("entities") or results.get("tags") or []
    else:
        items = results
    entities: list[Entity] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("id") or item.get("entity_id") or ""
        props = item.get("properties") or {}
        tags = [t.get("name", "") for t in item.get("tags") or [] if isinstance(t, dict)]
        types = item.get("types") or []
        entities.append(
            Entity(
                id=entity_id,
                name=item.get("name", ""),
                description=props.get("description", ""),
                entity_type=types[0] if types else item.get("type", ""),
                tags=tags,
                source=source,
                raw=item,
            )
        )
    return entities


Transport = Callable[[str, dict[str, str]], dict[str, Any]]


def _urllib_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise QlooError(f"Qloo API HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise QlooError(f"Qloo API unreachable ({exc.reason}) for {url}") from exc
    except json.JSONDecodeError as exc:
        raise QlooError(f"Qloo API returned non-JSON for {url}: {exc}") from exc


class QlooClient:
    """Live Qloo hackathon API client (stdlib only)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        transport: Transport = _urllib_transport,
    ) -> None:
        if not api_key:
            raise QlooError(
                "QLOO_API_KEY is not set. Request a hackathon key from the "
                "Qloo hackathon organizers, or run offline "
                "(QLOO_OFFLINE=1 / --offline) to use recorded fixtures."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.offline = False

    @classmethod
    def from_env(cls) -> "QlooClient":
        key = os.environ.get("QLOO_API_KEY", "").strip()
        if not key:
            raise QlooError(
                "QLOO_API_KEY is not set. Export it to call the live API, or "
                "set QLOO_OFFLINE=1 to run from recorded fixtures."
            )
        return cls(api_key=key, base_url=os.environ.get("QLOO_BASE_URL", DEFAULT_BASE_URL))

    # -- endpoints ------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(clean)}"
        return self.transport(url, {"X-Api-Key": self.api_key})

    def search_entities(self, query: str, types: list[str] | None = None) -> list[Entity]:
        if not query.strip():
            raise QlooError("search query must not be empty")
        params: dict[str, Any] = {"query": query}
        if types:
            params["types"] = ",".join(types)
        return extract_entities(self._get("/search", params), source="live")

    def insights(
        self,
        filter_type: str,
        signal_entities: list[str] | None = None,
        signal_tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[Entity]:
        if not filter_type.startswith("urn:entity:"):
            raise QlooError(f"filter_type must be a urn:entity:* value, got {filter_type!r}")
        params: dict[str, Any] = {"filter.type": filter_type, "take": limit}
        if signal_entities:
            params["signal.interests.entities"] = ",".join(signal_entities)
        if signal_tags:
            params["signal.interests.tags"] = ",".join(signal_tags)
        return extract_entities(self._get("/v2/insights", params), source="live")

    def tags(self, query: str | None = None) -> list[Entity]:
        params: dict[str, Any] = {}
        if query:
            params["filter.query"] = query
        return extract_entities(self._get("/v2/tags", params), source="live")


class OfflineQlooClient:
    """Fixture-backed drop-in for QlooClient — same interface, zero network.

    Serves the hand-recorded responses in ``taste_concierge/fixtures/`` and
    marks every entity ``source="fixture"`` so the app can say it is offline.
    Unknown lookups raise QlooError instead of silently inventing data.
    """

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR) -> None:
        self.fixtures_dir = fixtures_dir
        self.offline = True

    def _load(self, name: str) -> dict[str, Any]:
        path = self.fixtures_dir / name
        if not path.exists():
            raise QlooError(f"offline fixture missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def search_entities(self, query: str, types: list[str] | None = None) -> list[Entity]:
        catalog = self._load("search.json")
        record = catalog.get(query.strip().lower())
        if record is None:
            return []  # offline catalog is finite; no match is honest
        entities = extract_entities(record, source="fixture")
        if types:
            entities = [e for e in entities if e.entity_type in types]
        return entities

    def insights(
        self,
        filter_type: str,
        signal_entities: list[str] | None = None,
        signal_tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[Entity]:
        if not filter_type.startswith("urn:entity:"):
            raise QlooError(f"filter_type must be a urn:entity:* value, got {filter_type!r}")
        fixture = _INSIGHTS_FIXTURES.get(filter_type)
        if fixture is None:
            raise QlooError(f"no offline insights fixture for {filter_type!r}")
        entities = extract_entities(self._load(fixture), source="fixture")
        return entities[:limit]

    def tags(self, query: str | None = None) -> list[Entity]:
        entities = extract_entities(self._load("tags.json"), source="fixture")
        if query:
            entities = [e for e in entities if query.lower() in e.name.lower()]
        return entities


def make_client(prefer_offline: bool | None = None) -> QlooClient | OfflineQlooClient:
    """Pick a client honestly: offline fixtures when asked, when
    ``QLOO_OFFLINE=1``, or when no API key is configured; live otherwise."""
    if prefer_offline is None:
        prefer_offline = os.environ.get("QLOO_OFFLINE", "").strip() == "1"
    if prefer_offline or not os.environ.get("QLOO_API_KEY", "").strip():
        return OfflineQlooClient()
    return QlooClient.from_env()


def client_label(client: QlooClient | OfflineQlooClient) -> str:
    if client.offline:
        return "OFFLINE — recorded Qloo fixtures (no live API key)"
    base = getattr(client, "base_url", DEFAULT_BASE_URL)
    return f"live Qloo API @ {base}"
