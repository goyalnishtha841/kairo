"""Kairo API.

Run:  uvicorn server.app:app --reload --port 8000     (from the repo root)
Serves the built UI from web/dist at / when present.
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
for sub in ("events", "ai"):
    sys.path.insert(0, str(ROOT / sub))

import copilot  # noqa: E402
import insights  # noqa: E402

app = FastAPI(title="Kairo")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def clip_dir(clip_id):
    d = (OUT / clip_id).resolve()
    if d.parent != OUT.resolve() or not (d / "timeline.json").exists():
        raise HTTPException(404, f"clip {clip_id} not processed")
    return d


def processed():
    return sorted(p.parent.name for p in OUT.glob("*/timeline.json"))


def parse_clips(clips):
    ids = [c for c in (clips or "").split(",") if c] or processed()
    for c in ids:
        clip_dir(c)
    return ids


@app.get("/api/clips")
def list_clips():
    out = []
    for c in processed():
        d = OUT / c
        tl = json.loads((d / "timeline.json").read_text())
        m = json.loads((d / "metrics.json").read_text()) if (d / "metrics.json").exists() else {}
        fr = [e for e in tl["events"] if e["severity"] != "green"]
        out.append({"clip_id": c, "duration_s": tl["duration_s"], "steps": len(tl["steps"]),
                    "friction_events": len(fr), "has_video": (d / "web.mp4").exists(), "metrics": m})
    return out


@app.get("/api/clips/{clip_id}/timeline")
def get_timeline(clip_id: str):
    return json.loads((clip_dir(clip_id) / "timeline.json").read_text())


@lru_cache(maxsize=16)
def _compact_hands(path, mtime):
    h = json.loads(Path(path).read_text())
    # [t, [[id, [[x,y]x21]], ...]] - small enough to stream to the browser for the live overlay
    return {"fps": h["fps"], "frames": [[f["t"], [[hd["id"], [[round(p[0], 3), round(p[1], 3)] for p in hd["lm"]]]
                                                 for hd in f["hands"]]] for f in h["frames"]]}


@app.get("/api/clips/{clip_id}/hands")
def get_hands(clip_id: str):
    p = clip_dir(clip_id) / "hands.json"
    return _compact_hands(str(p), p.stat().st_mtime)


@app.get("/api/report")
def get_report(clips: str = "", shift_hours: float = 8.0):
    return insights.analyse(parse_clips(clips), shift_hours)


class Ask(BaseModel):
    question: str
    clips: list[str] = []
    engine: str = "auto"


@app.post("/api/ask")
def ask(body: Ask):
    ids = parse_clips(",".join(body.clips))
    return copilot.ask(body.question, ids, body.engine)


@app.get("/api/engine")
def engine():
    return {"engine": copilot.available_engine()}


@app.get("/media/{clip_id}/web.mp4")
def media_video(clip_id: str):
    p = clip_dir(clip_id) / "web.mp4"
    if not p.exists():
        raise HTTPException(404, "no web proxy; run pipeline.py")
    return FileResponse(p, media_type="video/mp4")  # Starlette handles Range requests


@app.get("/media/{clip_id}/frames/{name}")
def media_frame(clip_id: str, name: str):
    p = (clip_dir(clip_id) / "frames" / name).resolve()
    if p.parent != (OUT / clip_id / "frames").resolve() or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")
