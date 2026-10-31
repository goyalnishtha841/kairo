"""Kairo API.

Run:  uvicorn server.app:app --reload --port 8000     (from the repo root)
Serves the built UI from web/dist at / when present.
"""
import json
import queue
import re
import shutil
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT))
for sub in ("events", "ai", "perception"):
    sys.path.insert(0, str(ROOT / sub))

import compare  # noqa: E402
import copilot  # noqa: E402
import insights  # noqa: E402
import proficiency  # noqa: E402
import quality  # noqa: E402
import recommend  # noqa: E402
import skill_profile  # noqa: E402
import verify  # noqa: E402

CLIP_ID_RE = re.compile(r"^[\w.-]{1,80}$")

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


@app.get("/api/proficiency")
def get_proficiency(clip: str):
    clip_dir(clip)
    cache = {}
    res = proficiency.score(clip, cache)
    res["curve"] = proficiency.station_curve(res["station"], cache)
    return res


@app.get("/api/quality")
def get_quality(clip: str, ref: str = ""):
    clip_dir(clip)
    if ref:
        clip_dir(ref)
    cache = {}
    res = quality.score(clip, ref or None, cache)
    res["station_scores"] = quality.station_scores(res["station"], ref or None, cache)
    return res


@app.get("/api/skill")
def get_skill(clip: str):
    clip_dir(clip)
    try:
        return skill_profile.profile(clip)
    except KeyError:
        raise HTTPException(404, f"no skill profile for {clip}")


@app.get("/api/simulate")
def get_simulate(clip: str, friction_type: str):
    if friction_type not in insights.RECOVERABLE:
        raise HTTPException(400, f"friction_type must be one of {sorted(insights.RECOVERABLE)}")
    return recommend.simulate(json.loads((clip_dir(clip) / "timeline.json").read_text()), friction_type)


@app.get("/api/accuracy")
def get_accuracy():
    p, h = OUT / "accuracy.json", OUT / "accuracy_heldout.json"
    if not p.exists():
        return None
    res = json.loads(p.read_text())
    if h.exists():
        res["heldout"] = json.loads(h.read_text())
    return res


@app.get("/api/verification")
def get_verification():
    """Temporal verification report (cached in outputs/verification.json; python perception/verify.py --report
    refreshes it, ~15 s)."""
    p = OUT / "verification.json"
    if not p.exists():
        p.write_text(json.dumps(verify.report(), indent=1))
    res = json.loads(p.read_text())
    res.pop("clips", None)
    return res


@app.get("/api/compare")
def get_compare(ref: str, target: str):
    clip_dir(ref), clip_dir(target)
    return compare.compare(ref, target)


# --------------------------------------------------------------------------- processing jobs
# One worker thread: perception is CPU-bound, so clips are processed one at a time.
JOBS: dict[str, dict] = {}
_queue: "queue.Queue[str]" = queue.Queue()


def _worker():
    import pipeline  # heavy (mediapipe); imported on first job

    while True:
        clip_id = _queue.get()
        job = JOBS[clip_id]
        job.update(state="running", started=time.time())
        try:
            pipeline.process(clip_id, stride=job.get("stride", 2))
            job.update(state="done", finished=time.time())
        except Exception as e:
            job.update(state="failed", error=f"{type(e).__name__}: {e}", finished=time.time())
        _queue.task_done()


threading.Thread(target=_worker, daemon=True).start()


@app.get("/api/raw")
def list_raw():
    done = set(processed())
    return [{"clip_id": p.stem, "size_mb": round(p.stat().st_size / 1e6, 1), "processed": p.stem in done,
             "job": JOBS.get(p.stem)} for p in sorted(RAW.glob("*.mp4"))]


@app.post("/api/process/{clip_id}")
def start_process(clip_id: str, stride: int = 2):
    if not CLIP_ID_RE.match(clip_id) or not (RAW / f"{clip_id}.mp4").exists():
        raise HTTPException(404, "no such raw clip")
    if JOBS.get(clip_id, {}).get("state") in ("queued", "running"):
        return JOBS[clip_id]
    JOBS[clip_id] = {"clip_id": clip_id, "state": "queued", "stride": max(1, min(stride, 6)),
                     "queued": time.time()}
    _queue.put(clip_id)
    return JOBS[clip_id]


@app.get("/api/jobs")
def list_jobs():
    return list(JOBS.values())


@app.post("/api/upload")
def upload(file: UploadFile = File(...)):
    stem = re.sub(r"[^\w.-]", "_", Path(file.filename or "upload").stem)[:60] or "upload"
    if not (file.filename or "").lower().endswith((".mp4", ".mov", ".mkv")):
        raise HTTPException(400, "upload an .mp4/.mov/.mkv video")
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"{stem}.mp4"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return start_process(stem)


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
