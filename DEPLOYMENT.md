# Deployment (live public demo)

The hackathon requires "a live, working app participants can try end-to-end…
hosted and fully published externally" (no local-only demos). This is the $0
path, validated end-to-end on 2026-10-08:

```bash
# 1. run the app (live once QLOO_API_KEY exists, offline honest mode otherwise)
QLOO_API_KEY=... python3 -m taste_concierge.web --live --port 8931

# 2. free public URL, no account needed
cloudflared tunnel --url http://127.0.0.1:8931 --no-autoupdate
#    -> prints https://<random>.trycloudflare.com
```

Validated: public URL returned 200 for `/`, `/api/state`, and POST
`/api/message` (chat round-trip) with the app in offline-fixture mode.

Operational notes:
- Quick-tunnel URLs change on every restart and die with the process. During
  the judging window (Nov 2–16) keep both processes alive; a watchdog cron
  should restart the tunnel and update the Devpost link if the URL changes.
- The Qloo key lives only in the server-side environment; responses are never
  persisted to the repo (Qloo API terms: no public caching of response data).
- `docs/index.html` (GitHub Pages) is a labeled static replay for reviewers
  who just want the shape of the thing — the tunnel URL is the functional demo.
