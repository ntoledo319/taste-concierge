# Deployment

Boss order (2026-10-08): **no public tunnels (cloudflared or similar) from
Nick's machine. Demos are hosted as static GitHub Pages only.**

- The public demo is `docs/index.html` on GitHub Pages
  (<https://ntoledo319.github.io/taste-concierge/>) — a labeled static replay
  of the real app's output.
- Judges who want to run the real thing: `git clone`, `python3 -m pytest`
  (40 offline tests), `python -m taste_concierge.cli --demo` (scripted), or
  `python -m taste_concierge.web` (interactive, offline fixtures by default).
- With a hackathon API key, `export QLOO_API_KEY=...` flips the same code to
  the live Qloo API (`https://hackathon.api.qloo.com`) — no code changes.
- The Qloo key is never shipped client-side and Qloo response data is never
  committed to this repo (Qloo API terms).
