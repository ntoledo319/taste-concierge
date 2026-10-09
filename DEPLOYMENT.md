# Deployment

## Live app (Vercel) — the judge-facing demo

**<https://taste-concierge.vercel.app>** — the real agent on the live Qloo
API, deployed 2026-10-08 on the existing Vercel account (hobby team,
serverless Python in `api/index.py`).

- **Key hygiene:** `QLOO_API_KEY` exists only as a Vercel production secret
  (`vercel env`). Never in the repo, never client-side, never printed.
- **Stateless:** the browser holds the resolved likes and resends them with
  each `POST /api/message`; any instance can answer.
- **Rate limiting:** 30 msgs/min per client IP + a per-instance daily POST
  budget (serverless best-effort, no shared store), 500-char message cap.
- `vercel.json` rewrites `/`, `/api/state`, `/api/message` → the function.
- Verified live end-to-end: real `/search` + `/v2/insights` in production,
  plan slots labeled `[live]`, 429s on burst.

Redeploy: `vercel --prod --yes --scope nicholas-toledos-projects`.

## Backup: static replay (GitHub Pages)

`docs/index.html` → <https://ntoledo319.github.io/taste-concierge/> — a
labeled offline fixture demo/replay for keyless browsing.

Boss order (2026-10-08): no public tunnels (cloudflared or similar) from
Nick's machine; external demos go on Vercel or GitHub Pages only.
