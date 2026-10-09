"""Vercel serverless deployment of taste-concierge (Qloo Agentic Hackathon).

Serves the live app at the project root URL:
  GET  /              -> chat page
  GET  /api/state     -> greeting + mode label
  POST /api/message   -> {message, likes[]} -> {reply, likes, plan, trail, mode}

Stateless by design: the browser keeps the resolved likes and resends them
with every message, so any instance can answer. The Qloo key lives only in
the QLOO_API_KEY Vercel env var — never in the repo, never client-side.

Rate limiting: per-instance sliding window per client IP (30 msgs/min),
a per-instance daily POST budget, 500-char message cap, 24-like cap.
Per-instance limits are best-effort (serverless has no shared store) but
bound how fast one instance can drain the hackathon key.
"""

from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taste_concierge.agent import TasteConciergeAgent
from taste_concierge.qloo_client import Entity, make_client

MAX_MSG_CHARS = 500
MAX_LIKES = 24
RATE_WINDOW_S = 60
RATE_MAX_PER_WINDOW = 30
DAILY_POST_BUDGET = 5000

_requests: dict[str, list[float]] = {}
_day = {"date": "", "count": 0}


def _client_ip(handler) -> str:
    return (handler.headers.get("x-forwarded-for") or "unknown").split(",")[0].strip()


def _rate_limited(ip: str) -> bool:
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day["date"], _day["count"] = today, 0
    _day["count"] += 1
    if _day["count"] > DAILY_POST_BUDGET:
        return True
    window = [t for t in _requests.get(ip, []) if now - t < RATE_WINDOW_S]
    if len(window) >= RATE_MAX_PER_WINDOW:
        _requests[ip] = window
        return True
    window.append(now)
    _requests[ip] = window
    return False


def _inject_likes(agent: TasteConciergeAgent, raw_likes) -> list[dict]:
    """Load client-supplied resolved likes into a fresh agent; returns the
    normalized list echoed back to the client."""
    clean = []
    for item in (raw_likes or [])[:MAX_LIKES]:
        try:
            ent = Entity(
                id=str(item["id"]),
                name=str(item["name"]),
                entity_type=str(item.get("entity_type", "")),
                tags=[str(t) for t in item.get("tags", [])][:50],
                source="live",
            )
            key = str(item["key"])
        except (KeyError, TypeError, AttributeError):
            continue
        agent.likes.setdefault(key, []).append(ent)
        clean.append({"key": key, "id": ent.id, "name": ent.name,
                      "entity_type": ent.entity_type, "tags": ent.tags})
    return clean


def _export_state(agent: TasteConciergeAgent, likes_clean: list[dict]) -> dict:
    return {
        "mode": f"Qloo: LIVE @ https://hackathon.api.qloo.com",
        "likes": likes_clean,
        "plan": [
            {"slot": p.slot, "name": p.entity.name, "why": p.why,
             "entity_id": p.entity.id, "source": p.source}
            for p in (agent.plan.picks if agent.plan else [])
        ],
        "trail": [
            {"endpoint": c.endpoint,
             "params": " ".join(f"{k}={v}" for k, v in c.params.items()),
             "source": c.source, "result_count": c.result_count}
            for c in agent.api_trail
        ],
    }


_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>taste-concierge — live demo (Qloo Agentic Hackathon)</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;font-family:ui-sans-serif,system-ui,sans-serif;background:#0b1020;color:#e6e9f2}
#chat{max-width:860px;margin:0 auto;display:flex;flex-direction:column;height:100vh}
header{padding:14px 20px;border-bottom:1px solid #232a45}
header h1{margin:0;font-size:16px}header small{color:#8b93b0}
.note{margin:12px 20px 0;padding:10px 14px;font-size:13px;background:#131a30;border:1px solid #2c3554;border-left:3px solid #f0a832;border-radius:6px;color:#c9d1e8}
#log{flex:1;overflow-y:auto;padding:16px 20px}
.msg{max-width:80%;padding:10px 14px;border-radius:14px;margin:6px 0;white-space:pre-wrap;line-height:1.45;font-size:14px}
.agent{background:#1c2440;border-bottom-left-radius:4px}
.you{background:#0d3b66;margin-left:auto;border-bottom-right-radius:4px}
form{display:flex;gap:8px;padding:12px 20px;border-top:1px solid #232a45}
input{flex:1;padding:10px 12px;border-radius:8px;border:1px solid #2c3554;background:#131a30;color:inherit;font-size:14px}
button{padding:10px 18px;border:0;border-radius:8px;background:#2f6df6;color:white;font-size:13px;cursor:pointer}
a{color:#6db3ff}
</style></head><body>
<div id="chat">
<header><h1>taste-concierge — live demo</h1><small id="mode">connecting…</small></header>
<p class="note">Live deployment of the <a href="https://github.com/ntoledo319/taste-concierge">taste-concierge</a> agent for the <a href="https://qloo.devpost.com/">Qloo Agentic Hackathon</a>. Every recommendation below comes from real calls to <code>hackathon.api.qloo.com</code> (the key is server-side only). Fixture/offline replay: <a href="https://ntoledo319.github.io/taste-concierge/">GitHub Pages backup</a>.</p>
<div id="log" aria-live="polite"></div>
<form id="f"><input id="m" autocomplete="off" placeholder='Try: "movies: Inception, music: Radiohead" — then "plan my evening"'><button>Send</button></form>
</div>
<script>
const log=document.getElementById('log'), f=document.getElementById('f'), m=document.getElementById('m');
let likes=[];
function add(role,text){const d=document.createElement('div');d.className='msg '+role;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;}
fetch('/api/state').then(r=>r.json()).then(s=>{document.getElementById('mode').textContent=s.mode;add('agent',s.greeting);});
f.addEventListener('submit',async ev=>{ev.preventDefault();const text=m.value.trim();if(!text)return;m.value='';add('you',text);
const r=await fetch('/api/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,likes:likes})});
const s=await r.json();
if(r.status===429){add('agent','Rate limit hit — the demo caps messages to protect the hackathon API key. Try again in a minute.');return;}
likes=s.likes||likes;
add('agent',s.reply||('error: '+(s.error||'unknown')));
});
</script></body></html>"""


class handler(BaseHTTPRequestHandler):  # Vercel Python runtime entry point
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body = _PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/state":
            agent = TasteConciergeAgent(make_client())
            self._json({"mode": "Qloo: LIVE @ https://hackathon.api.qloo.com",
                        "greeting": agent.greeting()})
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/message":
            self._json({"error": "not found"}, status=404)
            return
        if _rate_limited(_client_ip(self)):
            self._json({"error": "rate limited"}, status=429)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 64 * 1024)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            message = str(payload.get("message", ""))[:MAX_MSG_CHARS]
        except (ValueError, UnicodeDecodeError):
            self._json({"error": "bad json"}, status=400)
            return
        agent = TasteConciergeAgent(make_client())
        likes_clean = _inject_likes(agent, payload.get("likes"))
        reply = agent.handle(message)
        # export possibly-updated likes (new resolutions appended)
        all_likes = []
        for key, ents in agent.likes.items():
            for e in ents:
                all_likes.append({"key": key, "id": e.id, "name": e.name,
                                  "entity_type": e.entity_type, "tags": e.tags})
        self._json({"reply": reply, **_export_state(agent, all_likes)})
