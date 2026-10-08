"""Browser chat simulator (stdlib http.server) — the judge-friendly demo.

    python -m taste_concierge.web                 # offline fixtures, port 8080
    python -m taste_concierge.web --live          # real Qloo API (needs key)
    python -m taste_concierge.web --port 9000

Serves a single-page chat widget wired to the live agent, with a side panel
showing the evening plan and the full Qloo API trail behind every pick.
Offline fixtures are the default and the header says so.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .agent import CATEGORIES, TasteConciergeAgent
from .qloo_client import client_label, make_client

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>taste-concierge</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif;
         background: #0b1020; color: #e6e9f2; display: flex; height: 100vh; }
  #chat { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  header { padding: 14px 20px; border-bottom: 1px solid #232a45; }
  header h1 { margin: 0; font-size: 16px; }
  header small { color: #8b93b0; }
  #log { flex: 1; overflow-y: auto; padding: 16px 20px; }
  .msg { max-width: 75%; padding: 10px 14px; border-radius: 14px;
         margin: 6px 0; white-space: pre-wrap; line-height: 1.45; font-size: 14px; }
  .agent { background: #1c2440; border-bottom-left-radius: 4px; }
  .you { background: #0d3b66; margin-left: auto; border-bottom-right-radius: 4px; }
  form { display: flex; gap: 8px; padding: 12px 20px; border-top: 1px solid #232a45; }
  input { flex: 1; padding: 10px 12px; border-radius: 8px; border: 1px solid #2c3554;
          background: #131a30; color: inherit; font-size: 14px; }
  button { padding: 10px 18px; border: 0; border-radius: 8px; background: #2f6df6;
           color: white; font-size: 14px; cursor: pointer; }
  #panel { width: 360px; border-left: 1px solid #232a45; padding: 16px;
           overflow-y: auto; }
  #panel h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .08em;
              color: #8b93b0; }
  .state { font-size: 13px; padding: 6px 10px; border-radius: 6px;
           background: #1c2440; display: inline-block; margin-bottom: 10px; }
  .call { font-size: 12.5px; padding: 8px 10px; border-left: 3px solid #2f6df6;
          background: #131a30; margin: 6px 0; border-radius: 4px; word-break: break-all; }
  .call.fixture { border-color: #f0a832; }
  .call.live { border-color: #3fb950; }
  .pick { font-size: 12.5px; background: #131a30; padding: 8px 10px;
          border-radius: 6px; margin: 6px 0; }
  .pick b { color: #6db3ff; }
  .muted { color: #8b93b0; font-style: italic; font-size: 12.5px; }
  @media (max-width: 860px) {
    body { flex-direction: column; height: auto; }
    #log { min-height: 50vh; }
    #panel { width: auto; border-left: 0; border-top: 1px solid #232a45; }
  }
</style>
</head>
<body>
  <div id="chat">
    <header>
      <h1>taste-concierge — an evening planned by Qloo's taste graph</h1>
      <small id="mode"></small>
    </header>
    <div id="log"></div>
    <form id="f">
      <input id="m" autocomplete="off" placeholder="Try: movies: Inception and Spirited Away — then: plan my evening">
      <button>Send</button>
    </form>
  </div>
  <div id="panel">
    <h2>Evening plan</h2>
    <div id="plan"><span class="muted">no plan yet</span></div>
    <h2>Likes collected</h2>
    <div id="likes"><span class="muted">none yet</span></div>
    <h2>Qloo API trail</h2>
    <div id="trail"><span class="muted">none yet</span></div>
  </div>
<script>
const log = document.getElementById('log');
function esc(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function add(role, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.innerHTML = esc(text);
  log.appendChild(d); log.scrollTop = log.scrollHeight;
}
function render(s) {
  document.getElementById('mode').textContent = s.mode;
  document.getElementById('trail').innerHTML = s.trail.map(c =>
    `<div class="call ${c.source}"><b>GET ${c.endpoint}</b> ${esc(c.params)} → ${c.result_count} result(s) [${c.source}]</div>`
  ).join('') || '<span class="muted">none yet</span>';
  document.getElementById('likes').innerHTML = s.likes.map(l =>
    `<div class="pick"><b>${esc(l.slot)}</b> ${esc(l.name)}<br><small>${l.id} [${l.source}]</small></div>`
  ).join('') || '<span class="muted">none yet</span>';
  document.getElementById('plan').innerHTML = s.plan.length ? s.plan.map(p =>
    `<div class="pick"><b>${esc(p.slot)}:</b> ${esc(p.name)}<br>` +
    `<small>${esc(p.why)}</small><br><small>${p.entity_id} [${p.source}]</small></div>`
  ).join('') : '<span class="muted">no plan yet</span>';
}
fetch('/api/state').then(r => r.json()).then(s => { render(s); add('agent', s.greeting); });
document.getElementById('f').addEventListener('submit', async ev => {
  ev.preventDefault();
  const input = document.getElementById('m');
  const text = input.value.trim(); if (!text) return;
  input.value = ''; add('you', text);
  const r = await fetch('/api/message', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({message: text})});
  const s = await r.json();
  add('agent', s.reply); render(s);
});
</script>
</body>
</html>
"""


def _state_payload(agent: TasteConciergeAgent) -> dict:
    return {
        "mode": f"Qloo: {client_label(agent.client)} · phrasing: {agent.phraser_description}",
        "greeting": agent.greeting(),
        "trail": [
            {
                "endpoint": c.endpoint,
                "params": " ".join(f"{k}={v}" for k, v in c.params.items()),
                "source": c.source,
                "result_count": c.result_count,
            }
            for c in agent.api_trail
        ],
        "likes": [
            {"slot": cat.slot, "name": e.name, "id": e.id, "source": e.source}
            for cat in CATEGORIES
            for e in agent.likes.get(cat.key, [])
        ],
        "plan": [
            {
                "slot": p.slot,
                "name": p.entity.name,
                "why": p.why,
                "entity_id": p.entity.id,
                "source": p.source,
            }
            for p in (agent.plan.picks if agent.plan else [])
        ],
    }


def make_handler(agent: TasteConciergeAgent):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            pass

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = _PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/state":
                self._json(_state_payload(agent))
            else:
                self._json({"error": "not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/message":
                self._json({"error": "not found"}, status=404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                message = str(payload.get("message", ""))
            except (ValueError, UnicodeDecodeError):
                self._json({"error": "bad json"}, status=400)
                return
            reply = agent.handle(message)
            self._json({"reply": reply, **_state_payload(agent)})

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="taste-concierge-web",
        description="Browser chat simulator for the taste concierge agent.",
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="serve recorded fixtures (default)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="call the live Qloo API (requires QLOO_API_KEY)",
    )
    args = parser.parse_args(argv)

    agent = TasteConciergeAgent(make_client(prefer_offline=not args.live))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(agent))
    print(f"taste-concierge web demo on http://127.0.0.1:{args.port}")
    print(f"[Qloo: {client_label(agent.client)} · phrasing: {agent.phraser_description}]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
