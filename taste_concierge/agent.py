"""The concierge agent: taste interview in, explained evening plan out.

The agent interviews the user about what they like (movies, food, music,
books), resolves each like to a real Qloo entity via ``/search``, asks
``/v2/insights`` for cross-domain recommendations signaled on those likes,
and composes an evening plan where every pick names the signals that
produced it. Nothing is invented: every recommendation traces to a recorded
API call (live or fixture — always labeled) in ``agent.api_trail``.

Honest-AI phrasing: with ``OPENAI_API_KEY`` set, a stdlib OpenAI-compatible
adapter polishes the deterministic draft (facts are never delegated to the
LLM); without it the agent uses plain templates and says so.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .qloo_client import (
    Entity,
    OfflineQlooClient,
    QlooClient,
    QlooError,
    client_label,
)

Client = QlooClient | OfflineQlooClient


# ---------------------------------------------------------------------------
# Categories: how a user like maps to a Qloo entity type and a plan slot.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Category:
    key: str             # internal key
    urn: str             # Qloo filter.type / search type
    slot: str            # evening-plan slot label
    keywords: tuple[str, ...]  # words the parser listens for


CATEGORIES: tuple[Category, ...] = (
    Category("movie", "urn:entity:movie", "Movie", ("movie", "movies", "film", "films")),
    Category("dinner", "urn:entity:place", "Dinner", ("restaurant", "restaurants", "food", "dinner", "sushi", "ramen", "eat")),
    Category("music", "urn:entity:artist", "Nightcap soundtrack", ("music", "band", "bands", "artist", "artists", "album")),
    Category("book", "urn:entity:book", "Read before bed", ("book", "books", "novel", "read", "reading")),
)

_CATEGORY_BY_KEYWORD = {
    kw: cat for cat in CATEGORIES for kw in cat.keywords
}


@dataclass
class ApiCall:
    """One recorded Qloo call — the audit trail behind every pick."""

    endpoint: str
    params: dict[str, Any]
    source: str  # "live" | "fixture"
    result_count: int


@dataclass
class Pick:
    slot: str
    entity: Entity
    why: str
    signal_names: list[str]
    source: str  # "live" | "fixture"


@dataclass
class EveningPlan:
    picks: list[Pick] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # categories with no signal

    def render(self) -> str:
        if not self.picks:
            return "I couldn't build a plan yet — tell me some things you like first."
        lines = ["Here's your evening, built from Qloo's taste graph:"]
        for i, pick in enumerate(self.picks, 1):
            desc = f" — {pick.entity.description}" if pick.entity.description else ""
            lines.append(f"{i}. {pick.slot}: {pick.entity.name}{desc}")
            lines.append(f"   why: {pick.why}")
            lines.append(f"   entity id: {pick.entity.id} [{pick.source}]")
        if self.skipped:
            lines.append("(skipped, no likes given: " + ", ".join(self.skipped) + ")")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phrasing (honest-AI: deterministic by default, LLM polish only with a key)
# ---------------------------------------------------------------------------

class Phraser(Protocol):
    description: str

    def polish(self, draft: str) -> str: ...


class TemplatePhraser:
    description = "deterministic templates (no OPENAI_API_KEY configured)"

    def polish(self, draft: str) -> str:
        return draft


class LLMPhraser:
    """OpenAI-compatible chat adapter (stdlib urllib). Only rephrases the
    deterministic draft; it never sees or invents recommendation data beyond
    what the draft already contains, and any failure falls back to the draft."""

    description = "LLM phrasing via OPENAI_* env (facts stay deterministic)"

    def __init__(self) -> None:
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ["OPENAI_API_KEY"]
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def polish(self, draft: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": (
                    "You polish a concierge's reply. Keep every fact, name, id "
                    "and bracketed label exactly as given; only improve warmth "
                    "and flow. Return the rephrased text only."
                )},
                {"role": "user", "content": draft},
            ],
            "temperature": 0.4,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip() or draft
        except Exception:
            return draft


def make_phraser() -> tuple[Phraser, str]:
    if os.environ.get("OPENAI_API_KEY", "").strip():
        phraser: Phraser = LLMPhraser()
    else:
        phraser = TemplatePhraser()
    return phraser, phraser.description


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

# Two deterministic parse strategies:
# 1. Segmented: "movies: Inception and Spirited Away, music: Radiohead" —
#    a category keyword followed by ":" starts a segment that runs until the
#    next category keyword.
# 2. Free-form: "I love the movie Inception" / "my favorite band is
#    Radiohead" / "I'm into Dune".
_KW = r"movies?|films?|restaurants?|food|dinner|sushi|ramen|music|bands?|artists?|albums?|books?|novels?|reading"
_SEGMENT_RE = re.compile(rf"\b(?P<kw>{_KW})\s*[:=-]\s*", re.I)
_FREEFORM_RE = re.compile(
    rf"(?:i (?:really )?(?:like|love|enjoy)|my favou?rite(?:\s+\w+)?\s+is|i'm into|into)\s+"
    rf"(?:the\s+(?P<kw>{_KW})\s+)?(?P<names>[A-Z0-9][\w'’\-&.,() ]*?)\s*[.!]?$",
    re.I,
)

_PLAN_RE = re.compile(r"\b(plan|build|make|compose|suggest)\b.*\b(evening|night|plan)\b|\bplan my evening\b", re.I)

_SPLIT_RE = re.compile(r"\s*(?:,|\band\b|&|\|)\s*", re.I)


def _parse_likes(message: str) -> list[tuple[str | None, str]]:
    """Return (category-keyword-or-None, name) pairs from a message."""
    pairs: list[tuple[str | None, str]] = []
    segments = list(_SEGMENT_RE.finditer(message))
    if segments:
        for i, seg in enumerate(segments):
            end = segments[i + 1].start() if i + 1 < len(segments) else len(message)
            body = message[seg.end():end]
            for name in _SPLIT_RE.split(body.strip(" .;")):
                if name.strip():
                    pairs.append((seg.group("kw"), name.strip()))
        return pairs
    match = _FREEFORM_RE.search(message)
    if match:
        for name in _SPLIT_RE.split(match.group("names").strip(" .")):
            if name.strip():
                pairs.append((match.group("kw"), name.strip()))
    return pairs


class TasteConciergeAgent:
    """Interview → resolve → insights → explained evening plan."""

    def __init__(self, client: Client, phraser: Phraser | None = None) -> None:
        self.client = client
        if phraser is None:
            phraser, self.phraser_description = make_phraser()
        else:
            self.phraser_description = phraser.description
        self.phraser = phraser
        # category key -> resolved signal entities, in the order given
        self.likes: dict[str, list[Entity]] = {}
        self.api_trail: list[ApiCall] = []
        self.plan: EveningPlan | None = None
        self._seq = itertools.count(1)

    # -- introspection --------------------------------------------------------

    @property
    def mode_label(self) -> str:
        return client_label(self.client)

    def greeting(self) -> str:
        offline_note = (
            " Heads up: I'm running OFFLINE on recorded Qloo fixtures, so every "
            "pick below is labeled [fixture]."
            if self.client.offline
            else ""
        )
        return self.phraser.polish(
            "Hi — I'm your taste concierge. Tell me what you love and I'll "
            "plan an evening around it using Qloo's cultural taste graph: "
            "a dinner spot, a movie, a soundtrack, and a book, each pick "
            "explained by the exact signals behind it." + offline_note + "\n"
            "Try: \"movies: Inception and Spirited Away, music: Radiohead\" — "
            "then say \"plan my evening\"."
        )

    # -- conversation ----------------------------------------------------------

    def handle(self, message: str) -> str:
        if _PLAN_RE.search(message):
            return self._handle_plan_request()
        found = self._collect_likes(message)
        if found:
            return self.phraser.polish(found)
        return self.phraser.polish(
            "I didn't catch a like in that. Name a category and what you love, "
            "e.g. \"books: Dune\" or \"I love the restaurant Sushi Nakazawa\". "
            "When you're ready, say \"plan my evening\"."
        )

    # -- machinery --------------------------------------------------------------

    def _record(self, endpoint: str, params: dict[str, Any], results: list[Entity]) -> None:
        source = results[0].source if results else ("fixture" if self.client.offline else "live")
        self.api_trail.append(ApiCall(endpoint, params, source, len(results)))

    def _resolve(self, category: Category, name: str) -> Entity | None:
        results = self.client.search_entities(name, types=[category.urn])
        self._record("/search", {"query": name, "types": category.urn}, results)
        return results[0] if results else None

    def _collect_likes(self, message: str) -> str:
        additions: list[str] = []
        misses: list[str] = []
        for kw, name in _parse_likes(message):
            if kw is not None:
                category = _CATEGORY_BY_KEYWORD.get(kw.lower().rstrip("s")) or _CATEGORY_BY_KEYWORD.get(kw.lower())
                if category is None:
                    continue
                entity = self._resolve(category, name)
                if entity is None:
                    misses.append(name)
                    continue
                if any(e.id == entity.id for e in self.likes.get(category.key, [])):
                    continue
                self.likes.setdefault(category.key, []).append(entity)
                additions.append(f"{category.slot.lower()} like {entity.name} (id {entity.id})")
            else:
                found = self._resolve_any(name)
                if found is None:
                    misses.append(name)
                else:
                    category, entity = found
                    additions.append(f"{category.slot.lower()} like {entity.name} (id {entity.id})")
        parts: list[str] = []
        if additions:
            parts.append("Got it — I resolved " + "; ".join(additions) + " via Qloo /search.")
            missing = [c.slot.lower() for c in CATEGORIES if c.key not in self.likes]
            if missing:
                parts.append("Still open: " + ", ".join(missing) + ". Or say \"plan my evening\".")
            else:
                parts.append("I have all four categories — say \"plan my evening\".")
        if misses:
            parts.append(
                "I couldn't resolve: " + ", ".join(misses)
                + (" (the offline fixture catalog is finite)" if self.client.offline else " (Qloo /search returned nothing)")
                + "."
            )
        return " ".join(parts)

    def _resolve_any(self, name: str) -> tuple[Category, Entity] | None:
        """No category keyword: probe each category's search until one hits.
        Each probe is a real recorded call; on a hit the entity is stashed
        here so it isn't resolved twice."""
        for category in CATEGORIES:
            results = self.client.search_entities(name, types=[category.urn])
            self._record("/search", {"query": name, "types": category.urn}, results)
            if results:
                self.likes.setdefault(category.key, []).append(results[0])
                return category, results[0]
        return None

    def _handle_plan_request(self) -> str:
        if not self.likes:
            return self.phraser.polish(
                "Happy to — but I need at least one like first. Tell me a movie, "
                "restaurant, band or book you love."
            )
        self.plan = self._compose_plan()
        source_note = "[fixture]" if self.client.offline else "[live]"
        return self.phraser.polish(self.plan.render() + f"\n(all picks {source_note})")

    def _compose_plan(self, per_slot: int = 1) -> EveningPlan:
        plan = EveningPlan()
        for category in CATEGORIES:
            signals = self.likes.get(category.key)
            if not signals:
                plan.skipped.append(category.slot.lower())
                continue
            signal_ids = [e.id for e in signals]
            signal_names = [e.name for e in signals]
            try:
                results = self.client.insights(
                    filter_type=category.urn, signal_entities=signal_ids, limit=5
                )
            except QlooError as exc:
                plan.skipped.append(f"{category.slot.lower()} (Qloo error: {exc})")
                continue
            self._record(
                "/v2/insights",
                {"filter.type": category.urn, "signal.interests.entities": ",".join(signal_ids)},
                results,
            )
            for entity in results[:per_slot]:
                shared = sorted(set(entity.tags) & {t for s in signals for t in s.tags})
                shared_note = f" It shares your taste tags: {', '.join(shared)}." if shared else ""
                why = (
                    "Qloo /v2/insights ranked this from signal.interests.entities="
                    + ",".join(signal_ids)
                    + f" ({' + '.join(signal_names)})."
                    + shared_note
                )
                plan.picks.append(
                    Pick(
                        slot=category.slot,
                        entity=entity,
                        why=why,
                        signal_names=signal_names,
                        source=entity.source,
                    )
                )
        return plan

    # -- reporting ---------------------------------------------------------------

    def trail_summary(self) -> str:
        if not self.api_trail:
            return "no Qloo calls yet"
        lines = []
        for i, call in enumerate(self.api_trail, 1):
            params = " ".join(f"{k}={v}" for k, v in call.params.items())
            lines.append(f"{i}. GET {call.endpoint} {params} -> {call.result_count} result(s) [{call.source}]")
        return "\n".join(lines)
