"""Hand-tracking accuracy against human labels.

1) sample:  python eval/accuracy.py sample   -> eval/sample.json + labelling grids in outputs/eval/
   Frames are stratified: half where the tracker found hands, half where it found none (to catch misses).
2) label:   edit eval/labels.json: for each sample id ->
              {"gt": <wearer's hands visible: 0/1/2>, "correct": <tracked skeletons that sit on a wearer's hand>,
               "lr_ok": <of those, how many have the right Left/Right label>}
3) score:   python eval/accuracy.py score    -> outputs/accuracy.json (shown in the Shift Report)
"""
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
RAW = ROOT / "data" / "raw"
EVAL = Path(__file__).resolve().parent
BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
         (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]
COLOR = {"L": (60, 154, 255), "R": (255, 200, 60)}
PER_CLIP = 6
TILE = (480, 270)


def clips():
    return sorted(p.parent.name for p in OUT.glob("*/hands.json")
                  if not p.parent.name.startswith("zz-") and (RAW / f"{p.parent.name}.mp4").exists())


def sample():
    rng = random.Random(7)
    items = []
    for c in clips():
        fr = json.loads((OUT / c / "hands.json").read_text())["frames"]
        hit = [f for f in fr if f["hands"]]
        miss = [f for f in fr if not f["hands"]]
        k = PER_CLIP // 2
        pick = rng.sample(hit, min(k, len(hit))) + rng.sample(miss, min(PER_CLIP - min(k, len(hit)), len(miss)))
        for f in pick:
            items.append({"clip_id": c, "frame": f["frame"], "t": f["t"],
                          "tracked": [{"id": h["id"], "lm": h["lm"]} for h in f["hands"]]})
    rng.shuffle(items)  # mixed order so the labeller can't infer the tracker's answer from position
    for i, it in enumerate(items):
        it["id"] = i
    (EVAL / "sample.json").write_text(json.dumps(items))
    render_grids(items)
    print(f"{len(items)} frames sampled from {len(clips())} clips -> outputs/eval/grid_*.jpg")


def render_grids(items, per=8):
    d = OUT / "eval"
    d.mkdir(parents=True, exist_ok=True)
    caps = {}
    tiles = []
    for it in items:
        cap = caps.setdefault(it["clip_id"], cv2.VideoCapture(str(RAW / f"{it['clip_id']}.mp4")))
        cap.set(cv2.CAP_PROP_POS_FRAMES, it["frame"])
        ok, im = cap.read()
        im = cv2.resize(im if ok else np.zeros((270, 480, 3), np.uint8), TILE)
        for h in it["tracked"]:
            pts = (np.array(h["lm"])[:, :2] * TILE).astype(int)
            for a, b in BONES:
                cv2.line(im, tuple(pts[a]), tuple(pts[b]), COLOR[h["id"]], 2, cv2.LINE_AA)
            cv2.putText(im, h["id"], tuple(pts[0] + [6, 18]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR[h["id"]], 2)
        cv2.rectangle(im, (0, 0), (70, 34), (0, 0, 0), -1)
        cv2.putText(im, f"#{it['id']}", (6, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        tiles.append(im)
    for g in range(0, len(tiles), per):
        chunk = tiles[g:g + per]
        while len(chunk) % 4:
            chunk.append(np.zeros_like(tiles[0]))
        rows = [np.hstack(chunk[r:r + 4]) for r in range(0, len(chunk), 4)]
        cv2.imwrite(str(d / f"grid_{g // per:02d}.jpg"), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])


def score():
    items = {it["id"]: it for it in json.loads((EVAL / "sample.json").read_text())}
    labels = {int(k): v for k, v in json.loads((EVAL / "labels.json").read_text()).items()
              if v.get("correct") is not None}  # skip frames awaiting relabel
    det = gt = correct = lr_ok = 0
    frame_ok = 0
    for i, lab in labels.items():
        n_tr = len(items[i]["tracked"])
        det += n_tr
        gt += lab["gt"]
        correct += lab["correct"]
        lr_ok += lab["lr_ok"]
        frame_ok += int((n_tr > 0) == (lab["gt"] > 0))
    res = {
        "frames_labelled": len(labels),
        "clips": len({items[i]["clip_id"] for i in labels}),
        "detections": det, "ground_truth_hands": gt, "correct_detections": correct,
        "precision": round(correct / det, 3) if det else None,
        "recall": round(correct / gt, 3) if gt else None,
        "left_right_accuracy": round(lr_ok / correct, 3) if correct else None,
        "frame_presence_accuracy": round(frame_ok / len(labels), 3) if labels else None,
        "method": "Human-labelled frames, stratified half tracked / half untracked, across all processed clips.",
    }
    res["f1"] = (round(2 * res["precision"] * res["recall"] / (res["precision"] + res["recall"]), 3)
                 if res["precision"] and res["recall"] else None)
    base = EVAL / "baseline_accuracy.json"
    if base.exists():
        res["baseline"] = {k: v for k, v in json.loads(base.read_text()).items()
                           if k in ("precision", "recall", "f1", "left_right_accuracy", "frame_presence_accuracy")}
    (OUT / "accuracy.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return res


def refresh():
    """After re-running the tracker: pull new detections for the SAME frames, keep human ground truth,
    and re-render only frames whose detections changed (their correct/lr labels need a new look)."""
    items = json.loads((EVAL / "sample.json").read_text())
    labels = json.loads((EVAL / "labels.json").read_text())
    cache, changed = {}, []
    for it in items:
        fr = cache.setdefault(it["clip_id"], {f["frame"]: f for f in
                                              json.loads((OUT / it["clip_id"] / "hands.json").read_text())["frames"]})
        new = [{"id": h["id"], "lm": h["lm"]} for h in fr[it["frame"]]["hands"]]
        if len(new) != len(it["tracked"]) or any(
                a["id"] != b["id"] or np.abs(np.array(a["lm"])[0, :2] - np.array(b["lm"])[0, :2]).max() > 0.03
                for a, b in zip(sorted(new, key=lambda h: h["id"]), sorted(it["tracked"], key=lambda h: h["id"]))):
            changed.append(it["id"])
            labels[str(it["id"])].update(correct=None, lr_ok=None)
        it["tracked"] = new
    (EVAL / "sample.json").write_text(json.dumps(items))
    (EVAL / "labels.json").write_text(json.dumps(labels, indent=0))
    for f in (OUT / "eval").glob("grid_*.jpg"):
        f.unlink()
    render_grids([it for it in items if it["id"] in changed])
    print(f"{len(changed)} of {len(items)} frames changed -> relabel ids {changed}")


if __name__ == "__main__":
    {"sample": sample, "score": score, "refresh": refresh}[sys.argv[1]]()
