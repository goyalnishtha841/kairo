# Data, splits and how Kairo is tested

## 1. Do we train a model? No, and that is deliberate

Kairo trains no neural network. It combines:

| Part | What it is | Trained by us? |
|---|---|---|
| Hand landmarks | Google MediaPipe Hand Landmarker (pretrained) | No |
| Head motion | OpenCV optical flow (classical algorithm) | No |
| Activity states, friction, SOP steps | Rules on hand + head signals (`events/timeline.py`) | No, but thresholds are **calibrated** |
| Left/right hand | Geometric rule (`perception/hands.py: left_score`) | No, but 3 weights are **tuned** |
| Step names | Qwen vision model on Groq (pretrained) | No |
| Copilot | gpt-oss-120b on Groq (pretrained), tool calls over the timeline | No |

In 24 hours with under an hour of footage, training a model would overfit and be impossible to validate.
So we tune a handful of numbers on labelled data and test them on data we did not tune on.

## 2. Data we used

| Item | Amount |
|---|---|
| Footage available on the hackathon Drive | ~38 clips × 3 min ≈ 114 min (4 series) |
| Downloaded and processed | 19 clips × 3 min = **57 min** (~2 GB, ~103,000 frames at 30 FPS) |
| Frames the tracker analyses (every 2nd frame) | ~43,000 |
| Series covered | SGF00106 (carpentry, chair frames), SKL00089 (sorting / assembly at a table), mytronlabs-000003 (grinder / chisel work), mytronlabs-000060 |
| Human-labelled frames, **tuning set** | 90 frames from 15 clips (119 visible wearer hands) |
| Human-labelled frames, **held-out test set** | 48 frames from 3 clips never used in tuning: SKL00089-011, mytronlabs-000003-003, mytronlabs-000060-008 |

Footage stays on the laptop and is never committed (data rules). Only numbers (landmarks, labels, metrics) are in the repo.

## 3. The split

We have no training split, because nothing is trained. The split is between the data we tuned on and the data we report on:

```
                    ┌────────────────────────────┐
  15 clips ───────▶ │ TUNING / VALIDATION SET    │  90 labelled frames
                    │ choose detection threshold │  (used to pick numbers,
                    │ choose left/right weights  │   so scores here are optimistic)
                    └────────────────────────────┘
                    ┌────────────────────────────┐
  4 other clips ──▶ │ HELD-OUT TEST SET          │  labelled AFTER tuning was frozen
                    │ never looked at while      │  (this is the honest number)
                    │ tuning anything            │
                    └────────────────────────────┘
```

The split is **by clip**, not by frame, so neighbouring frames from the same moment can't leak from
tuning into testing. Frames in each set are **stratified**: half where the tracker found hands and half
where it found none, so missed hands are counted.

### How a frame is labelled
For each sampled frame, a person looks at the original image with the tracker's skeletons drawn on it and records:
- `gt`: how many of the wearer's own hands are visible (0, 1 or 2)
- `correct`: how many drawn skeletons sit on a real wearer hand
- `lr_ok`: of those, how many have the right Left/Right label

From these: **precision** = correct / drawn, **recall** = correct / visible, **F1**, **left/right accuracy**,
and **frame presence** ("hands in view?" right or wrong).

```bash
python eval/accuracy.py sample                    # tuning set (already done)
python eval/accuracy.py sample --set heldout MTL-SKL00089-011 ...   # held-out set
#   look at outputs/eval/*grid_*.jpg, fill eval/[heldout_]labels.json
python eval/accuracy.py score [--set heldout]     # -> outputs/accuracy[_heldout].json, shown in the Shift Report
```

## 4. Automated tests (139, run with `python -m pytest tests -q`)

| Suite | File | What it checks |
|---|---|---|
| End to end | `tests/test_e2e.py` (8) | Cuts a real 25 s clip and runs the whole pipeline. Checks that every output file exists, tracking quality (confidence, smoothing reduces jitter, FPS), valid landmarks, that the web video is H.264, the keyframes, and that the API serves the new clip: timeline, hands, video range requests, report, copilot. Checks the UI is served. **Uploads a video through the API and waits for the background worker.** |
| Data contracts | `tests/test_contracts.py` (59) | Every processed clip (19)'s timeline: valid event types and times, unique ids, states that cover the clip without overlaps, ordered steps. Insights maths: the breakdown sums to 100%, lost ≥ recoverable, recommendations sorted, **every piece of evidence points at a real event**, and extrapolation scales with shift length. |
| AI | `tests/test_ai.py` (12) | The rules copilot answers 6 question types with citations to real clips and times. Citation clean-up handles LLM output. **Live Groq answers are grounded** (skipped without a key). The comparator scores a clip vs itself at 100%, and catches a missing, a swapped and a slower step in a synthetic case. |
| Recommendations | `tests/test_recommend.py` (6) | Confidence grows with evidence and spread, consistency beats erratic durations, the ROI formula, full evidence records sorted by ROI, simulation removes exactly the recoverable share and shifts later time, and the simulate API. |
| Proficiency | `tests/test_proficiency.py` (7) | Baseline is leave-one-out and same-station, every point is explained, below-baseline metrics cite timestamps, the median workflow scores near 50, more friction scores lower, levels follow the config, and the API. |
| Temporal verification | `tests/test_verify.py` (11) | A one-frame dropout is bridged on the motion path, long dropouts and off-path or resized reappearances are not, teleports split a track, a weak one-frame blip is rejected while confident or repeated short detections are kept, bridged frames are presence but not motion. On real data: detection accounting, raw tracks reproduce the saved timeline, **held-out labels: recall up with no labelled real hand rejected and no precision loss**, and the API. |
| Skill profile | `tests/test_skill.py` (10) | SPARC rates one smooth reach above a corrected one, sub-movement peaks ignore tracking ripple, a repeated grasp needs the same spot within 2 s, **head motion is removed** from hand velocity, k-means is deterministic. On real data: every recording gets a pattern and explanation, **labels never contradict the expertise index**, beginner-tone features cite timestamps, the API and the copilot. |
| Collaboration | `tests/test_collaboration.py` (11) | **No event** for: a worker passing, crossing close, standing silently while work continues, talking while working independently, a noisy environment with nobody there, or a one-frame flicker. **Detected** for: real collaboration (confirmed, ≥0.90), the same without speech (only "possible"), and occluded faces (one event, not split). The speech threshold adapts to noise, and writing to the timeline is idempotent. |
| Units and safety | `tests/test_units.py` (8) | Hand identity survives label flips. The Left/Right geometry works. The ego-hand threshold works. One-Euro reduces jitter without lag. Head-motion direction is right. The API rejects path traversal, unknown clips and non-video uploads. |

## 5. How to test it yourself (manual checklist)

Start: `python -m uvicorn server.app:app --port 8000`, then open **http://localhost:8000**.

| # | Do this | You should see |
|---|---|---|
| 1 | **Analyze**: press play | Hand skeletons on the wearer's hands only (orange = left, blue = right); coworkers' hands are ignored |
| 2 | Click a **red** part of the timeline | The video jumps there; a callout says why ("Searching 7.4 s, head scanning right") |
| 3 | Click an event in the right-hand list | Same jump; the event highlights while it plays |
| 4 | Copilot: "Where did the worker search for tools?" | An answer with ▶ timestamps; clicking one seeks the video; the badge top-right says Groq |
| 5 | Copilot: "Which step took the longest?" / "What should we change?" | Grounded answers with timestamps |
| 6 | **SOP** tab | Step cards with keyframes, duration, hand, and step names like "Cut wood piece · jigsaw" |
| 7 | **Compare**: pick the same clip twice | 100% adherence, everything "Matches" |
| 8 | **Compare**: pick two different clips | Missing / extra / out-of-order rows, findings with links |
| 9 | **Layout & Savings** | A minutes-per-shift headline, a station map, ranked fixes; evidence chips jump to the moment |
| 10 | **Shift Report** | KPIs, the bottleneck step, the friction table, **hand-tracking accuracy (tuning vs held-out)** and per-clip quality |
| 11 | **Clips**: upload a short .mp4 | Status goes Queued → Processing… → Processed; the clip appears in every tab |
| 12 | Stop your internet and ask the copilot something | It falls back to the rules engine and still answers with timestamps |

## 6. Known limits
- Savings are linear extrapolations from the minutes observed, and the UI says so.
- "Idle" = hands out of view with the head still. It can include talking or watching a machine.
- The comparator needs two clips of the **same task**. Consecutive chunks of one long job are different tasks.
- Accuracy is measured on a small set of hand-labelled frames. It's an honest estimate, not a benchmark.
