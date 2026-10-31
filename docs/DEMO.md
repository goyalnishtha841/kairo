# Kairo: 3-minute demo

**Goal:** a buyer from NVIDIA, Siemens or Bosch leaves believing three things. The number is real, it can be checked, and it can be deployed tomorrow.

Before going on stage:
- `python -m uvicorn server.app:app --port 8000`, then open http://localhost:8000. Everything is precomputed; keep a screen recording as backup.
- The badge top right should say **Groq**. Offline, the rules engine answers with the same citations.
- Pre-select recording **MTL-SGF00106-021**, which has the most friction and the collaboration event.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Deck cover | "A factory has a thousand hours of head-camera footage. Nobody watches it. Engineers sample one percent." |
| 0:15 | **Clips** tab: upload a short clip | "An engineer drops in a video. No training data, no labelling." *(Then switch to the precomputed clip.)* |
| 0:30 | **Analyze**: play 3 s with the overlay | "Kairo tracks the wearer's own hands, not coworkers', and labels every second: working, searching, waiting." |
| 0:45 | Click a **red** block | The video jumps. "Searching, 7 seconds, head scanning right. Every claim is a timestamp you can check." |
| 1:00 | Copilot: **"Which recommendation has the highest ROI?"** | "It can only read the timeline, so every answer links to evidence. It can't invent anything." Click a ▶. |
| 1:20 | **Impact** tab | "About **€16,000 per station per year**. The top fix: remove waiting time, 153 events in 15 of 19 recordings, 83% confidence." Click **Simulate fix**: "Today 3:00, with the fix 2:16." |
| 1:50 | **Proficiency** tab | "Each recording is compared with its station's baseline. This one scores 31: hands-on time 0.4x baseline, searching 4.2x, and here are the moments. We score the workflow, never the worker." |
| 2:15 | Blue band on the Analyze timeline, or the Shift Report | "Collaboration only when several signals agree: a coworker close, facing the wearer, work paused, then resumed. One event in 57 minutes. We would rather miss one than invent one." |
| 2:30 | **Shift Report** → accuracy | "Measured on clips we never tuned on: 91% precision and 93% left/right hand accuracy. 115 automated tests." |
| 2:45 | Close | "It runs on a laptop CPU, footage never leaves the site, and it works on your video today. Kairo turns footage nobody watches into fixes worth €16,000 per station per year." |

**If something breaks:** the copilot falls back to rules offline, and the screen recording covers everything else.

Hard questions and model answers are in [STRATEGY.md §6](STRATEGY.md#6-twenty-hard-judge-questions).
