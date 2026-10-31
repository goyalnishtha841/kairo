# Kairo: 3-minute demo script

Before going on stage:
- Start the app: `python -m uvicorn server.app:app --port 8000`, open http://localhost:8000
- Everything is precomputed, so nothing processes live. Keep a screen recording as a backup.
- Check that the engine badge (top right) says **Groq**. If the network is down, the rules engine still answers with citations.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Deck: cover, problem, idea | "Factories record hours of head-camera video nobody watches. Kairo watches it and scores the workstation, never the worker." |
| 0:30 | **Analyze** tab, best clip, overlay on | Play 3 s. "Hand tracking on a laptop CPU. Coworkers' hands are filtered out; left and right come from geometry." |
| 0:45 | Click a **red block** on the timeline | Video jumps; callout reads "Searching 7.4 s". "Every second is labelled: working, searching, walking away, idle." |
| 1:05 | Copilot: "Where did the worker search for tools?" | Click a ▶ timestamp. "It can only query the timeline, so every answer links to the moment." |
| 1:25 | **SOP** tab | "The video writes its own SOP: steps, keyframes, tools, named by a vision model." |
| 1:40 | **Compare** tab | Reference vs check: "missing, out-of-order and slower steps, with an adherence score." |
| 2:00 | **Layout & Savings** | Read the headline: "about 60 min per shift recoverable; the biggest levers are cutting waiting (~28 min) and staging tools in the front zone (~15 min), based on 57 minutes of footage." Click one evidence chip. |
| 2:25 | **Shift Report**, scroll to accuracy | "We hand-labelled 138 frames. On clips we never tuned on: 91% precision, 59% recall, and 93% left/right, up from 47%." |
| 2:45 | Deck: tested, close | "87 automated tests on real footage. Kairo turns footage nobody watches into fixes a factory can make tomorrow." |

Likely questions:
- **How accurate is the tracking?** Shift Report → accuracy table (`python eval/accuracy.py score` reproduces it).
- **How do you know "search" is really search?** We checked frames by hand, and every claim links to a moment anyone can verify.
- **Privacy?** Results are per station and never score a worker. Processing runs locally, and footage is never committed.
- **Are the savings real?** They're linear extrapolations from the observed minutes, with the assumptions shown on screen.
