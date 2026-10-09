# Live Qloo API verification — 2026-10-08

Hackathon API key arrived by email 2026-10-08 ~19:51 ET. Both checks below ran
against `https://hackathon.api.qloo.com` with the key in `QLOO_API_KEY`
(env-only, never stored or printed).

## 1. Endpoint round-trip (`scripts/verify_live.py`)

- `GET /search` for "Inception" → **6 live results** (top: `Inception`,
  id `18B098FD-3D84-4609-BFF3-ADF9A0B00E40`, source=live).
- `GET /v2/insights?filter.type=urn:entity:movie&signal.interests.entities=18B098FD…`
  → **5 live picks**: The Matrix (`C6046119…`), Memento (`C67F4628…`),
  The Prestige (`C79652B1…`), Batman Begins (`9FD8AB95…`), Fight Club
  (`DCF2D39D…`). The client code is unchanged from the fixture-tested build.

## 2. Full agent run, live mode (`python -m taste_concierge.cli`, key set)

- `movies: Inception, music: Radiohead` resolved via live `/search`
  (Inception `18B098FD…`, Radiohead `70CAE5BF…`).
- `plan my evening` produced live plans, every pick labeled `[live]`, e.g.
  Movie: **The Matrix** from signal `18B098FD…` with the full shared taste-tag
  list; Nightcap soundtrack: **Thom Yorke** from signal `70CAE5BF…`.
- API trail shows 4 live calls (2× `/search`, 2× `/v2/insights`), 6/10/5/5
  results.

Offline fixture mode remains available and labeled for judges without a key
(`QLOO_OFFLINE=1`); live mode flips on with `QLOO_API_KEY` — same code path.
