"""Recompute jitter metrics from saved hands.json (strictly consecutive processed frames only).

Usage: python eval/recompute_jitter.py            # all processed clips; updates metrics.json in place
"""
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "outputs"


def jitter(frames, key, stride, w, h):
    vals = []
    for hid in ("L", "R"):
        run, last = [], None
        for f in frames:
            hd = next((x for x in f["hands"] if x["id"] == hid), None)
            if hd is None or (last is not None and f["frame"] - last != stride):
                if len(run) >= 3:
                    vals.append(run)
                run = []
            if hd is not None:
                run.append(np.array(hd[key])[:, :2] * [w, h])
                last = f["frame"]
            else:
                last = None
        if len(run) >= 3:
            vals.append(run)
    per = [float(np.linalg.norm(np.diff(np.array(r), 2, axis=0), axis=-1).mean()) for r in vals]
    return round(float(np.mean(per)), 3) if per else None


def main():
    for m_path in sorted(OUT.glob("*/metrics.json")):
        m = json.loads(m_path.read_text())
        hp = m_path.parent / "hands.json"
        if not hp.exists():
            continue
        frames = json.loads(hp.read_text())["frames"]
        w, h = m["processed_resolution"]
        raw, sm = jitter(frames, "lm_raw", m["stride"], w, h), jitter(frames, "lm", m["stride"], w, h)
        m.update(jitter_px_raw=raw, jitter_px_smoothed=sm,
                 jitter_reduction_pct=round(100 * (1 - sm / raw), 1) if raw and sm else None)
        m_path.write_text(json.dumps(m, indent=2))
        print(f"{m_path.parent.name}: jitter {raw} -> {sm} px ({m['jitter_reduction_pct']}%)")


if __name__ == "__main__":
    main()
