# taste-concierge

An agentic evening planner built on the [Qloo](https://qloo.com/) cultural
taste graph. Tell it what you love — a movie, a restaurant, a band, a book —
and it plans your evening: dinner, a film, a nightcap soundtrack, and a read
before bed. **Every pick is explained by the exact Qloo signals behind it**,
and every recommendation traces to a recorded Qloo API call (or a clearly
labeled offline fixture).

Entry for the **Qloo Agentic Hackathon** (Devpost, deadline Oct 30):
<https://qloo.devpost.com/>

**Status: Offline fixtures by default; live Qloo verification happens when
the hackathon API key arrives (requested 2026-10-08).** The client is built
against the documented hackathon API (`https://hackathon.api.qloo.com`,
`X-Api-Key` auth, `GET /search`, `GET /v2/insights`, `GET /v2/tags`) and
switches to live mode the moment `QLOO_API_KEY` is set — no code changes.

## Run it

Python 3.11+, stdlib only. No dependencies to install.

```bash
# scripted non-interactive demo (offline fixtures)
python3 -m taste_concierge.cli --demo

# interactive chat (offline fixtures)
python3 -m taste_concierge.cli --offline

# browser chat simulator at http://127.0.0.1:8080 (offline by default)
python3 -m taste_concierge.web

# live Qloo API — once the hackathon key arrives
export QLOO_API_KEY=<hackathon-key>
python3 -m taste_concierge.cli          # or: python3 -m taste_concierge.web --live
```

Try in the chat: `movies: Inception and Spirited Away`, then
`I love the restaurant Sushi Nakazawa`, `music: Radiohead`, `books: Dune`,
then `plan my evening`.

Tests (40, all offline, no network):

```bash
python3 -m pytest
```

Static demo replay (GitHub Pages):
<https://ntoledo319.github.io/taste-concierge/>

## Architecture

```
taste_concierge/
  qloo_client.py   stdlib urllib client: search_entities(), insights(), tags().
                   X-Api-Key header auth, GET-only, query-string params.
                   OfflineQlooClient serves recorded fixtures with the same
                   interface and labels every entity source="fixture".
  agent.py         TasteConciergeAgent: deterministic interview parser,
                   resolves likes via /search, plans via /v2/insights,
                   explains each pick with the signal entity ids used.
                   Every call recorded in agent.api_trail (the audit trail).
                   Honest-AI phrasing: deterministic templates by default;
                   optional LLM polish only when OPENAI_API_KEY is set
                   (facts are never delegated to the LLM).
  cli.py           argparse CLI: --offline (default without key), --demo.
  web.py           stdlib http.server single-page chat demo with a side
                   panel showing the plan and the full Qloo API trail.
  fixtures/        hand-recorded, realistically-shaped Qloo responses
                   (search.json, insights_{movie,place,artist,book}.json,
                   tags.json) so the whole app runs with zero network.
tests/             40 pytest tests: param building, auth header, error
                   paths, agent flow end-to-end on fixtures, plan
                   composition, offline labeling, web endpoints.
docs/              static replay of the --demo transcript (GitHub Pages).
```

### Qloo API usage (per the hackathon developer guide)

- Base URL `https://hackathon.api.qloo.com` (override with `QLOO_BASE_URL`).
- Auth: `X-Api-Key: <key>` header — not Bearer, not a query param.
- `GET /search?query=<name>&types=urn:entity:movie` resolves names to
  Qloo entity ids.
- `GET /v2/insights?filter.type=urn:entity:place&signal.interests.entities=<ids>`
  returns cross-domain taste recommendations. All four plan slots (movie,
  place, artist, book) are built from these two endpoints.
- `GET /v2/tags` lists valid tag ids.
- Legacy `/recs` / `/recommendations` are intentionally not used.

### Honest offline mode

The hackathon key arrives by email after registration, so the app is built
against recorded fixtures shaped like the documented responses. Offline mode
is always **declared**: the CLI header, the greeting, every entity, and every
pick say `[fixture]`. Unresolvable names return "I couldn't resolve" — the
agent never invents entities. Setting `QLOO_API_KEY` (and not `QLOO_OFFLINE=1`)
flips the same code paths to the live API.

## License

MIT
