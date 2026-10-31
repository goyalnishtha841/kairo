"""Factory Digital Twin Analytics (USP 12): a narrated, chronological timeline for one clip -- the
same steps/events/states Kairo already measures, formatted as a story a supervisor can skim.

Times are relative to the start of the clip (mm:ss), the same convention as every citation in Kairo.
If a real shift start time is supplied, entries are also labelled with a wall-clock time; without one
we never invent a wall-clock time.

Usage: python events/digital_twin.py <clip_id> [--shift-start HH:MM]
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t  # noqa: E402

IDLE_MIN_S = 5.0  # shorter idle spells are noise for a narrated timeline


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def narrate(clip_id, shift_start=None):
    """shift_start: optional 'HH:MM' wall-clock time the clip began."""
    tl = load(clip_id)
    base = None
    if shift_start:
        h, m = (int(x) for x in shift_start.split(":"))
        base = dt.datetime(2000, 1, 1, h, m)

    def label_t(t):
        if base is not None:
            return f"{(base + dt.timedelta(seconds=t)).strftime('%H:%M')} ({fmt_t(t)})"
        return fmt_t(t)

    entries = [{"t": 0.0, "t_label": label_t(0.0), "event": "Started", "detail": "Clip begins",
                "cite": f"[{clip_id}@00:00]"}]
    for s in tl["steps"]:
        entries.append({"t": s["t_start"], "t_label": label_t(s["t_start"]), "event": s["label"],
                         "detail": f"{s['duration_s']:.0f}s, {s['hand']} hand",
                         "cite": f"[{clip_id}@{fmt_t(s['t_start'])}]"})
    for e in tl["events"]:
        if e["type"] in ("collaboration", "possible_collaboration"):
            entries.append({"t": e["t_start"], "t_label": label_t(e["t_start"]), "event": "Conversation",
                             "detail": e["note"], "cite": f"[{clip_id}@{fmt_t(e['t_start'])}]"})
    for s in tl["states"]:
        if s["state"] == "idle" and (s["t_end"] - s["t_start"]) >= IDLE_MIN_S:
            entries.append({"t": s["t_start"], "t_label": label_t(s["t_start"]), "event": "Machine / worker idle",
                             "detail": f"{s['t_end'] - s['t_start']:.0f}s",
                             "cite": f"[{clip_id}@{fmt_t(s['t_start'])}]"})
    entries.append({"t": tl["duration_s"], "t_label": label_t(tl["duration_s"]), "event": "Finished",
                     "detail": "Clip ends", "cite": f"[{clip_id}@{fmt_t(tl['duration_s'])}]"})
    entries.sort(key=lambda e: e["t"])
    return {"clip_id": clip_id, "duration_s": tl["duration_s"], "timeline": entries}


if __name__ == "__main__":
    ss = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--shift-start" else None
    print(json.dumps(narrate(sys.argv[1], ss), indent=1))
