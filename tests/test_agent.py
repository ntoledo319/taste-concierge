"""Agent flow: interview → resolve → insights → explained plan, all offline."""

from __future__ import annotations

from taste_concierge.agent import TasteConciergeAgent, _parse_likes


def test_greeting_says_offline(agent):
    greeting = agent.greeting()
    assert "OFFLINE" in greeting
    assert "fixture" in greeting


def test_parse_segmented_message():
    pairs = _parse_likes("movies: Inception and Spirited Away, music: Radiohead")
    assert ("movies", "Inception") in pairs
    assert ("movies", "Spirited Away") in pairs
    assert ("music", "Radiohead") in pairs


def test_parse_freeform_with_category():
    assert _parse_likes("I love the restaurant Sushi Nakazawa") == [
        ("restaurant", "Sushi Nakazawa")
    ]


def test_parse_freeform_without_category():
    assert _parse_likes("I'm into Dune") == [(None, "Dune")]


def test_collect_like_resolves_via_search(agent):
    reply = agent.handle("movies: Inception")
    assert "Inception" in reply
    assert agent.likes["movie"][0].name == "Inception"
    search_calls = [c for c in agent.api_trail if c.endpoint == "/search"]
    assert search_calls and search_calls[0].params["query"] == "Inception"
    assert search_calls[0].source == "fixture"


def test_unresolvable_like_is_honest(agent):
    reply = agent.handle("movies: Zqxwv Notreal")
    assert "couldn't resolve" in reply
    assert "movie" not in agent.likes


def test_plan_requires_at_least_one_like(agent):
    reply = agent.handle("plan my evening")
    assert "need at least one like" in reply
    assert agent.plan is None


def test_full_flow_composes_plan_with_all_slots(agent):
    agent.handle("movies: Inception and Spirited Away")
    agent.handle("I love the restaurant Sushi Nakazawa")
    agent.handle("music: Radiohead")
    agent.handle("books: Dune")
    reply = agent.handle("plan my evening")
    plan = agent.plan
    assert plan is not None
    slots = {p.slot for p in plan.picks}
    assert slots == {"Movie", "Dinner", "Nightcap soundtrack", "Read before bed"}
    assert "Blade Runner 2049" in reply
    assert "Ippudo Westside" in reply
    assert "Portishead" in reply
    assert "The Three-Body Problem" in reply


def test_every_pick_explains_its_signals(agent):
    agent.handle("movies: Inception and Spirited Away")
    agent.handle("plan my evening")
    pick = agent.plan.picks[0]
    assert "signal.interests.entities=" in pick.why
    assert "Inception" in pick.why and "Spirited Away" in pick.why
    assert pick.entity.id  # traces to a real (fixture) entity id
    assert pick.source == "fixture"


def test_every_pick_traces_to_a_recorded_insights_call(agent):
    agent.handle("movies: Inception")
    agent.handle("music: Radiohead")
    agent.handle("plan my evening")
    insights_calls = [c for c in agent.api_trail if c.endpoint == "/v2/insights"]
    assert len(insights_calls) == 2
    for call in insights_calls:
        assert call.params["filter.type"].startswith("urn:entity:")
        assert "signal.interests.entities" in call.params
        assert call.result_count > 0


def test_offline_plan_is_labeled(agent):
    agent.handle("books: Dune")
    reply = agent.handle("plan my evening")
    assert "[fixture]" in reply


def test_partial_likes_skip_empty_slots(agent):
    agent.handle("books: Dune")
    agent.handle("plan my evening")
    plan = agent.plan
    assert len(plan.picks) == 1
    assert plan.picks[0].slot == "Read before bed"
    assert "movie" in plan.skipped and "dinner" in plan.skipped


def test_freeform_probe_finds_category(agent):
    reply = agent.handle("I'm into Dune")
    assert "Dune" in reply
    assert agent.likes["book"][0].name == "Dune"


def test_unparseable_message_gets_guidance(agent):
    reply = agent.handle("hello there")
    assert "didn't catch" in reply


def test_shared_tags_appear_in_explanation(agent):
    # Blade Runner 2049 shares the "sci-fi" tag with the Inception signal.
    agent.handle("movies: Inception")
    agent.handle("plan my evening")
    assert "sci-fi" in agent.plan.picks[0].why


def test_trail_summary_lists_calls(agent):
    agent.handle("movies: Inception")
    agent.handle("plan my evening")
    summary = agent.trail_summary()
    assert "/search" in summary and "/v2/insights" in summary
    assert "[fixture]" in summary
