#!/usr/bin/env python3
"""Live Qloo API verification for taste-concierge (run when the hackathon key arrives).

  QLOO_API_KEY=<key> python3 scripts/verify_live.py

Does one real /search and one real /v2/insights round-trip against
https://hackathon.api.qloo.com and prints a JSON evidence block for the repo
record (LIVE-VERIFICATION.md). The key is never printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taste_concierge.qloo_client import QlooClient


def main() -> int:
    client = QlooClient.from_env()
    evidence: dict[str, object] = {"base_url": getattr(client, "base_url", "n/a")}

    found = client.search_entities("Inception", types=["urn:entity:movie"])
    evidence["search_inception"] = [
        {"name": e.name, "id": e.id, "source": e.source} for e in found[:3]
    ]
    print(f"[live] /search Inception -> {len(found)} result(s)")

    if not found:
        print("[live] no entities returned; check response shape against fixtures")
        print(json.dumps(evidence, indent=2))
        return 1

    picks = client.insights(
        "urn:entity:movie", signal_entities=[found[0].id], limit=5
    )
    evidence["insights_movie_from_inception"] = [
        {"name": e.name, "id": e.id, "source": e.source} for e in picks[:5]
    ]
    print(f"[live] /v2/insights movie <- Inception -> {len(picks)} pick(s)")

    print("\n=== LIVE VERIFICATION EVIDENCE (paste into LIVE-VERIFICATION.md) ===")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
