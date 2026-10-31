# WorkFlow AI — AI Process Improvement Copilot

> Instead of evaluating workers, WorkFlow AI evaluates the workstation.

Egocentric factory video → hand tracking → event timeline → friction map, auto-SOP,
SOP comparison, layout recommendations, timeline-grounded copilot, shift report.

## Data rules (read first)
- **Never commit footage, frames, or screenshots.** `data/`, `outputs/` and all media are git-ignored.
- Show results only on the common demo clips. Delete cloud uploads after the event.

## Layout
```
perception/   A — hands.py (MediaPipe + identity + One-Euro + metrics), tools, head motion
events/       B — timeline engine, friction detectors, layout optimizer
ai/           C — SOP generator, comparator, copilot, shift report
web/          D — React app (video + timeline + heatmap + chat)
schema/       timeline contract + mock_timeline.json  ← everyone codes against this
data/raw/     source clips (ignored)
outputs/      per-clip results (ignored)
```

## Setup
```bash
pip install -r requirements.txt
python -m gdown --folder "<drive folder url>" -O data/raw --continue
```

## Run hand tracking
```bash
python perception/hands.py data/raw/<clip>.mp4 --stride 2 --max-seconds 60 --render
```
Outputs `outputs/<clip>/hands.json`, `metrics.json`, `overlay.mp4`.
Metrics reported: detection rate, per-hand presence, mean confidence, jitter raw vs smoothed (px),
identity label overrides, processing FPS.
