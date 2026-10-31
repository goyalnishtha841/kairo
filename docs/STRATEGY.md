# Kairo: principal-engineer review, strategy and plan

## 0. The judge lens

> *If I had 3 minutes to convince NVIDIA, Siemens or Bosch to buy this, what would impress them most?*

A buyer at that level has seen many AI dashboards. What moves them:

1. **A money number they can verify.** "~60 min per shift recoverable" means nothing without the evidence. Every number must click through to the video moment it came from.
2. **Measured accuracy on data we did not tune on.** Most hackathon teams quote model confidence. We quote human-labelled precision/recall on held-out clips. That is our strongest credibility asset.
3. **Deployability.** Runs on a laptop CPU, footage never leaves the site, and it works on *their* video (upload → result in minutes). There is no training data to collect.
4. **Training value without surveillance.** "This workflow deviates from the station baseline here" is sellable to works councils (Bosch, Siemens are in Germany). "This worker is slow" is not.

Every decision below is tested against: **memorable, believable, deployable**. A feature that is memorable but not believable (a rendered 3D factory unrelated to the footage) is cut. A feature that is believable only if it's precise (collaboration) ships tuned for precision, or not at all.

## 1. Assumptions challenged

| Assumption in the brief | Verdict | Why |
|---|---|---|
| "YOLO World is in the stack" | **False, so we remove the claim** | It was planned, never built. Claiming it is a fake feature. Tool names currently come from vision captions on keyframes. |
| Timeline should hold "tool picked / released" | **Not yet** | That needs a tool detector. Emitting these events from hand speed alone would fabricate evidence. Roadmap item. |
| Interactive 3D factory landing page with conveyors and robot arms | **Cut for the hackathon** | Our footage is carpentry, table assembly and grinding. A synthetic factory unrelated to the data reads as fake to industrial judges and costs ~1 day. Replaced by a HUD treatment of the real product. Roadmap: digital twin built *from* the station map. |
| "Nothing analyses raw video twice" | **Keep the spirit, refine the rule** | The expensive pass (hands at 15 FPS) runs once. Collaboration needs people, faces and audio, so a cheap 2 FPS pass plus audio is added as a *perception module* writing `social.json`. The timeline consumes both. |
| Collaboration via conversation classification | **Event detection only** | Transcribing workers' speech is a privacy and works-council problem and is error-prone in factory noise. We detect high-confidence collaboration *events* from multiple signals. Speech-content classification goes on the roadmap, opt-in. |
| Proficiency "Advanced / Needs Training" | **Score the workflow, not the person** | A baseline per station (the median of clips of the same task series), normalized deviations, an explainable 0–100 score. The labels are configurable thresholds on the workflow, never the worker. |
| Confidence ">0.90" numbers | **Only where we measured them** | Recommendation confidence comes from evidence volume and detector precision, and the method is stated. We never show a confidence we can't explain. |

## 2. Product audit

**Strong (highlight):**
- Timeline-grounded copilot. Every answer cites timestamps, and the offline fallback means the demo can't fail.
- Click-to-evidence everywhere: the friction map, recommendations, copilot, comparator.
- Measured hand-tracking accuracy on held-out clips (91% precision, 93% left/right).
- Upload → processed clip in minutes on a CPU.

**Weak (improve):**
- Recommendations lack confidence, money, and a "what if" view. *(Fixed in this round: ROI + confidence + before/after simulation.)*
- No way to say how a workflow compares with the station norm. *(Fixed: Proficiency Engine.)*
- Idle is ambiguous: talking, waiting, and hands below the camera's view all count. *(Partly fixed: collaboration events now explain some idle time.)*
- The comparator needs same-task clips. Our clips are consecutive chunks of one job.
- Step names depend on the Groq daily quota.

**Fake / remove:** the YOLO-World mention, and any slide implying tool pick/release detection.

**WOW moment:** clicking a recommendation's money figure and landing on the exact second where the waste happens, then seeing the timeline *with that waste removed* (simulation). It is a number, its proof and its fix in one gesture.

## 3. Engineering audit (54 findings)

Severity: **H** = fix before demo, **M** = fix soon, **L** = nice to have. ✅ = fixed in this round.

### Architecture
1. **H** ✅ Recommendation logic and savings maths live in one function (`insights.analyse`), so they're hard to extend. Split into a recommendation module with an explicit evidence model.
2. **H** ✅ No module answers "how does this workflow compare to normal?". The Proficiency Engine is missing.
3. **M** The timeline schema mixes `states`, `events`, `steps` and `signals` without versioning. Add `schema_version`.
4. **M** The step boundary rule (gaps ≥ 1.5 s) is generic. Per-station config is needed.
5. **M** All thresholds are module constants. Move them to one `config.py`/YAML per station.
6. **M** `insights.analyse` recomputes everything on every API call (no cache).
7. **L** Event `cycle_id` is always null. True cycle segmentation is missing (needs repeated-task footage).
8. **M** The perception output (`hands.json`, ~1.6 MB/clip) is JSON. Use npz/parquet at scale.
9. **L** No plugin interface for new detectors (tool detector, pose).
10. **M** ✅ Collaboration has no signals at all. Add a social perception module (people, faces, voice activity).

### Folder structure and naming
11. **M** The repo folder is `workflow-ai` while the product is Kairo. Rename the repo.
12. **L** The `perception/` and `events/` modules use `sys.path` hacks instead of a package (`kairo/`).
13. **L** `events/` holds analysis (insights, compare), not events. Rename to `analysis/`.
14. **L** `ai/env.py` shadows the generic name `env`. Use `kairo.config`.
15. **L** Tests import modules via path manipulation in `conftest.py`.

### API
16. **H** No authentication. Fine for a local demo; a blocker for deployment.
17. **M** `/api/report` has no pagination or clip limit; 1000 clips would be slow.
18. **M** No API versioning (`/api/v1`).
19. **M** Errors return plain strings, not a structured error model.
20. **L** No OpenAPI response models (Pydantic) for most endpoints.
21. **M** Upload has no size limit and no content sniffing (it trusts the extension).
22. **M** Job state is in memory and lost on restart.
23. **L** No rate limiting on `/api/ask` (each call costs LLM tokens).

### Security and privacy
24. **H** The Groq key was pasted in chat twice. Rotate both keys after the event.
25. **M** CORS is hard-coded to localhost:5173. Make it configurable.
26. **M** Path traversal guards exist and are tested; keep the tests.
27. **M** Copilot prompt injection: answers are tool-grounded, but the user question goes to the LLM unfiltered.
28. **M** Faces may appear in keyframes. Blur faces in saved frames.
29. **L** No audit log of who asked what.
30. ✅ The collaboration module stores only voice *activity* (yes/no per 30 ms), never audio or words.

### Testing
31. **M** No load or performance tests.
32. **M** No frontend tests (component or end-to-end browser).
33. **M** The e2e test takes ~1 min; there's no fast/slow test split marker.
34. **L** No property-based tests for the timeline segmentation.
35. **H** ✅ The new modules (proficiency, collaboration, recommendations) need unit and scenario tests, including collaboration false-positive scenarios.
36. **M** Event-level accuracy (is "search" really search?) is not yet measured, only hand tracking.

### Performance
37. **M** Perception is single-process, ~20 FPS at stride 2. Clips could run in parallel across cores.
38. **M** The web proxy re-encodes the full clip (~50 MB). It could stream HLS or use a lower bitrate.
39. **L** `hands.json` is loaded fully for the overlay (~400 KB per request). Use a binary format or range requests.
40. **L** No GPU path (MediaPipe GPU delegate) for site servers.

### State management (frontend)
41. **M** App state lives in one component with prop drilling. It needs a small store (Zustand) as views grow.
42. **L** No URL routing; tabs and the selected clip aren't linkable.
43. **L** Report and clip lists refetch with no caching (SWR/React Query).

### Developer experience
44. **M** No one-command start (`make dev` / `docker compose up`).
45. **M** No linting or formatting config (ruff, prettier).
46. **L** No pre-commit hook preventing media commits (we rely on `.gitignore`).
47. **L** No type checking (mypy / TypeScript).
48. **L** Logs from MediaPipe flood stdout.

### Deployment
49. **H** No Dockerfile. Edge deployment is the selling point, so ship a container.
50. **M** No GPU/edge build (Jetson) story yet.
51. **M** No retention policy for processed outputs.
52. **L** No health endpoint for orchestration.

### Product / AI quality
53. **H** ✅ Recommendations show no confidence or money. Buyers think in € and payback.
54. **M** Captions (step names) can be wrong; there's no human-correction loop.

## 4. Prioritization

Scored 1–5 (effort: 5 = cheapest).

| Improvement | Hackathon impact | Effort | Judge appeal | Demo value | Total | Decision |
|---|---|---|---|---|---|---|
| Recommendation engine v2: observation, evidence, confidence, € ROI, before/after simulation | 5 | 4 | 5 | 5 | **19** | **Build** |
| Workflow Proficiency Engine: baseline, deviations, 0–100, fingerprint radar | 5 | 3 | 5 | 5 | **18** | **Build** |
| Collaboration Intelligence (precision-first, multi-signal) | 4 | 2 | 5 | 4 | **15** | **Build, conservative** |
| UI: "Impact" HUD for the new modules | 4 | 3 | 4 | 5 | **16** | **Build (focused)** |
| Copilot tools for the new modules | 3 | 5 | 3 | 4 | **15** | **Build** |
| Remove the fake YOLO-World claim | 3 | 5 | 3 | 1 | 12 | **Do** |
| Dockerfile for edge deployment | 3 | 4 | 4 | 1 | 12 | Next |
| 3D factory digital twin landing | 3 | 1 | 4 | 4 | 12 | **Cut** (not believable on this footage) |
| Speech transcription + intent classification | 2 | 2 | 3 | 2 | 9 | **Cut** (privacy, noise, no value without precision) |
| Tool detector (YOLO-World) + pick/release events | 4 | 1 | 4 | 3 | 12 | Roadmap |

## 5. Rewritten 3-minute demo

| Time | Show | Say |
|---|---|---|
| 0:00 | Deck cover | "A factory has 1,000 hours of head-camera footage. Nobody watches it. Engineers sample 1%." |
| 0:15 | **Clips** tab: upload a clip | "An engineer drops in a video. No training, no labelling." |
| 0:30 | **Analyze**: the timeline fills, hand overlay | "Kairo tracks the wearer's hands, not coworkers', and labels every second: working, searching, waiting." |
| 0:50 | Click a red event | The video jumps. "Searching, 7 s, head scanning right. Every claim is a timestamp you can check." |
| 1:05 | Copilot: "Which recommendation has the highest ROI?" | It answers with € and timestamps. "It can only read the timeline, so it can't make things up." |
| 1:25 | **Impact** tab: the top recommendation | "Observation, evidence across N events, confidence, minutes and € per year." Click **Simulate**: the timeline with that waste removed. |
| 1:55 | **Proficiency**: fingerprint radar | "Each recording is compared with the station's baseline: where this workflow deviates, and by how much. The workflow, not the worker." |
| 2:15 | **Collaboration** events | "Only high-confidence collaboration: another person close, facing, voice activity, work paused, then resumed. We would rather miss one than invent one." |
| 2:30 | **Shift Report** accuracy table | "Measured on clips we never tuned on: 91% precision, 93% left/right." |
| 2:45 | Close | "On a laptop, on-site, today: about €16,000 per station per year. Kairo turns footage nobody watches into fixes you can make tomorrow." |

## 6. Twenty hard judge questions

1. **How accurate is it, really?** We hand-labelled 138 frames. On 3 clips never used for tuning: 91% precision, 59% recall, 93% left/right. The misses are mostly extreme close-ups and hands at the fisheye edge. We publish the method and the script.
2. **Recall is 59%. Isn't that low?** Recall is per frame. Activity decisions use 0.5 s windows, and a hand seen in most frames of a window still counts as working. Precision matters more: a false hand would create false "work". Raising recall is our next step (a second detection pass on the bottom crop of the frame).
3. **How do you know "searching" is really searching?** Hands are out of view while the head scans, measured with optical flow. We checked the events against the footage, and every event links to its seconds, so a sceptic can verify. Event-level precision is the next metric we will publish.
4. **Isn't this worker surveillance?** Outputs are per station and per workflow. There is no worker identity or ranking, and processing is on-premises. Proficiency compares a *recording* with the station baseline.
5. **What does it cost to deploy?** A laptop or edge box per site. No GPU needed, no data labelling, and LLM costs are cents per shift (optional; an offline mode exists).
6. **Why not train a model?** With an hour of footage, training would overfit and couldn't be validated. Pretrained perception plus transparent rules plus measured accuracy is the honest design. Training comes when a customer provides labelled hours.
7. **Where do the savings numbers come from?** Friction seconds × the share a fix can remove (shown on screen) × extrapolation to a shift. It's conservative and the assumptions are visible; a customer can edit them.
8. **How is the confidence of a recommendation computed?** From evidence volume (number of events, consistency of duration) and the measured precision of the underlying detector. It's a formula, not a model's opinion.
9. **What happens with a new station type?** Upload clips. The baseline is learned from them as the median of recordings, with no retraining.
10. **Could the LLM hallucinate?** It can only call three query tools over the timeline. Answers are normalised and every cited timestamp is parsed and checked against the clip. Tests verify that citations point to real moments.
11. **What if the internet is down?** The copilot falls back to a deterministic engine with the same citations. Perception is fully local.
12. **How do you avoid false collaboration events?** Multi-signal voting (a person nearby, a face toward the wearer, voice activity, work paused), a minimum duration, hysteresis and a confidence threshold. Below threshold we say nothing.
13. **Why not transcribe conversations?** Privacy, works-council approval, and factory noise. The event itself tells an engineer where to look; content is opt-in on the roadmap.
14. **How does it scale to 1,000 hours?** About 20 FPS per CPU core at stride 2, so roughly 0.15 core-hours per hour of footage. 1,000 hours is ~150 core-hours: a weekend on one 16-core box.
15. **Why MediaPipe and not a bigger model?** It runs on CPU at real time, it's robust on hands, and we measured it. A bigger model is a drop-in behind the same interface when GPUs are available.
16. **What's proprietary here?** The timeline contract, the ego-hand filter and egocentric left/right geometry, the evidence-grounded recommendation model, and the evaluation harness. Data network effects come from per-station baselines.
17. **How do you handle fisheye distortion?** Today we measure in normalised image space, and accuracy is quoted on that footage. Undistortion before detection is on the roadmap and should raise edge recall.
18. **Does it work on other industries?** Anything with hand-centric work: assembly, packaging, maintenance, labs. Our 4 footage series already span carpentry, assembly and grinding.
19. **How would it integrate with our systems?** A REST API and JSON timelines, plus exports to MES/BI. Recommendations map to kaizen tickets.
20. **What would you build next with our footage?** Event-level evaluation on your stations, a tool detector fine-tuned on your tools, true cycle segmentation, then a digital twin of each station built from its measured layout.

## 7. Roadmap

| Horizon | Goal | Key deliverables |
|---|---|---|
| **Hackathon** | A believable, measured, deployable demo | Timeline engine, friction map, SOP + comparator, ROI recommendations with simulation, Proficiency Engine, precision-first collaboration, grounded copilot, held-out accuracy |
| **3 months** | First pilot station | Docker / edge box, auth, per-station config, event-level accuracy, a tool detector (YOLO-World fine-tuned), true cycle segmentation, face blurring, a human correction loop for step names |
| **6 months** | Multi-station pilot | Station baselines across shifts, kaizen ticket export (MES / Jira), a learning-curve view per station, GPU path, retention and audit logs |
| **1 year** | Product | Multi-site deployment, an SOP library with versioning, digital twin of each station from measured layouts, an opt-in speech-intent layer with works-council templates |
| **3 years** | Platform | A workflow foundation model trained on customer-consented hours, closed-loop optimisation (simulate a layout change, verify after the change), robot-teaching data export |
