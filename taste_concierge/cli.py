"""Interactive / scripted demo CLI.

    python -m taste_concierge.cli --offline            # interactive, fixtures
    python -m taste_concierge.cli --demo               # scripted, non-interactive
    python -m taste_concierge.cli                      # live Qloo API
                                                       # (QLOO_API_KEY required)

Offline mode (default when no key is configured) serves recorded fixtures
from taste_concierge/fixtures/ and says so in every reply — nothing is faked.
"""

from __future__ import annotations

import argparse
import sys

from .agent import TasteConciergeAgent
from .qloo_client import QlooError, client_label, make_client

# A complete scripted journey: four likes across all categories, then the
# plan request. Deterministic under the template phraser + fixtures.
DEMO_TURNS = [
    "movies: Inception and Spirited Away",
    "I love the restaurant Sushi Nakazawa",
    "music: Radiohead",
    "books: Dune",
    "plan my evening",
]


def build_agent(prefer_offline: bool | None) -> TasteConciergeAgent:
    return TasteConciergeAgent(make_client(prefer_offline))


def _print_agent(text: str) -> None:
    for line in text.splitlines():
        print(f"  Agent: {line}")


def run_demo(agent: TasteConciergeAgent) -> int:
    """Run the scripted taste interview end-to-end, non-interactively."""
    print(f"[demo] Qloo: {client_label(agent.client)}")
    print(f"[demo] phrasing: {agent.phraser_description}")
    _print_agent(agent.greeting())
    for turn in DEMO_TURNS:
        print(f"  You:   {turn}")
        _print_agent(agent.handle(turn))
    print("\n=== QLOO API TRAIL ===")
    print(agent.trail_summary())
    return 0


def run_interactive(agent: TasteConciergeAgent) -> int:
    print(f"[Qloo: {client_label(agent.client)}]")
    print(f"[phrasing: {agent.phraser_description}]")
    print("[type 'quit' to exit]\n")
    _print_agent(agent.greeting())
    while True:
        try:
            message = input("  You:   ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.lower() in ("quit", "exit"):
            break
        if not message:
            continue
        _print_agent(agent.handle(message))
    print("\n=== QLOO API TRAIL ===")
    print(agent.trail_summary())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="taste-concierge",
        description="Agentic evening planner built on the Qloo cultural "
        "taste graph (Qloo Agentic Hackathon entry).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="run fully offline against recorded Qloo fixtures",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run the scripted interview (non-interactive); implies --offline",
    )
    args = parser.parse_args(argv)

    prefer_offline = True if (args.offline or args.demo) else None
    try:
        agent = build_agent(prefer_offline)
    except QlooError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.demo:
        return run_demo(agent)
    return run_interactive(agent)


if __name__ == "__main__":
    raise SystemExit(main())
