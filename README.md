# Kairo: AI Process Improvement Copilot

> Instead of evaluating workers, Kairo evaluates the workstation.

Egocentric factory video → hand tracking + head motion → event timeline → friction map,
auto-SOP, layout recommendations with minutes-per-shift savings, a timeline-grounded copilot,
and a shift report.

## Data rules (read first)
- **Never commit footage, frames, or screenshots.** `data/`, `outputs/` and all media are git-ignored.
- Show results only on the common demo clips. Delete cloud uploads after the event.

See [docs/OVERVIEW.md](docs/OVERVIEW.md) for the problem statement and architecture, [docs/TESTING.md](docs/TESTING.md) for data, splits and how to test, and [docs/DEMO.md](docs/DEMO.md) for the 3-minute demo.

## Layout
```
perception/   hands.py (MediaPipe + L/R identity + One-Euro + metrics), ego_motion.py, social.py (people, faces, voice activity), web_proxy.py
events/       timeline.py (states, friction, SOP steps), insights.py (shift report), recommend.py (evidence,
              confidence, ROI, simulation), proficiency.py (workflow vs station baseline), collaboration.py
              (precision-first collaboration events), compare.py (SOP comparator), config.py (EUR, thresholds)
ai/           copilot.py (Groq -> Claude -> rules), sop_labels.py (vision step names), env.py
server/       FastAPI: /api/clips, /api/clips/{id}/timeline|hands, /api/report, /api/ask, /api/proficiency,
              /api/simulate, /api/compare, /api/accuracy, /api/upload, /api/process, /media
web/          React + Vite HUD: Analyze · Impact · Proficiency · SOP · Compare · Shift Report · Clips
tests/        140 integration + unit tests (python -m pytest tests -q)
schema/       timeline contract + mock_timeline.json
pipeline.py   runs everything for one or more clips
```

## Setup
```bash
pip install -r requirements.txt
npm --prefix web install
cp .env.example .env        # then put your GROQ_API_KEY in .env (git-ignored, never commit it)
python -m gdown --folder "<drive folder url>" -O data/raw --continue
```

## Process clips
```bash
python pipeline.py --all --skip-existing          # or: python pipeline.py MTL-SGF00106-021 ...
python ai/recaption.py                            # fill in missing step names; waits out Groq rate limits
```
Per clip this writes `outputs/<clip>/hands.json`, `metrics.json`, `timeline.json`, `frames/`, `web.mp4`
(H.264 browser proxy), plus `outputs/shift_report.json` over all processed clips.
CPU only: ~25 FPS at 640 px with `--stride 2` (about 2 min per 3-min clip).

## Run the app
```bash
python -m uvicorn server.app:app --port 8000
npm --prefix web run dev                          # http://localhost:5173
```
For a single-server demo: `npm --prefix web run build`, then just run uvicorn and open http://localhost:8000.

### AI engines (picked automatically: Groq → Claude → rules)
- **Groq** (`GROQ_API_KEY` in `.env`): copilot on `openai/gpt-oss-120b` with tool calls over the timeline;
  SOP step names + tools from keyframes with `qwen/qwen3.8-27b` (vision).
- **Claude** (`claude-opus-5-5`): same tools, used when Anthropic credentials exist and no Groq key is set.
- **Rules**: deterministic, offline fallback; always cites timestamps.

The LLM never sees video: it only queries the event timeline, and every moment it mentions is a
`[clip@mm:ss]` citation the UI turns into a seek link.

## How detection works
| Signal | Source |
|---|---|
| Own hands only | ego-hand filter: palm length < 3.3% of frame width = someone else's hand, rejected |
| Working | at least one of the wearer's hands in view (MediaPipe, 0.5 s median filter) |
| Searching | hands out of view + head scanning (optical-flow pan/tilt), < 8 s |
| Walking away | the same, longer than 8 s |
| Idle / waiting | hands out of view, head still |
| Hesitation | hand stalls 1–3 s between two movements |
| Extra reach | one movement whose path is > 3x the straight line |
| SOP steps | work blocks split by gaps ≥ 1.5 s, keyframe at the block middle |

Savings = friction seconds × recoverable fraction (stated in the UI) × shift-length extrapolation.
