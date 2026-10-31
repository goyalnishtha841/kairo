"""Timeline-grounded copilot.

Every answer comes from the timeline/report and carries citations [clip_id@mm:ss] that the UI turns
into seek links. Engines, tried in this order with `engine="auto"`:
  * groq   - gpt-oss-120b on Groq with tools over the timeline (GROQ_API_KEY in .env)
  * claude - Claude with the same tools (Anthropic credentials)
  * rules  - deterministic intent matching, no key needed (always available, and the fallback)
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "events"))
sys.path.insert(0, str(ROOT / "ai"))
import env  # noqa: E402,F401  (loads .env)
from insights import analyse, fmt_t, load  # noqa: E402
import proficiency  # noqa: E402
import skill_profile  # noqa: E402
import attention  # noqa: E402
import baseline_drift  # noqa: E402
import collab_score  # noqa: E402
import digital_twin  # noqa: E402
import knowledge_graph  # noqa: E402
import memory  # noqa: E402
import root_cause  # noqa: E402
import safety  # noqa: E402
import search as factory_search  # noqa: E402
import shift_summary  # noqa: E402
import sop  # noqa: E402

MODEL = "claude-opus-5-5"
GROQ_MODEL = "openai/gpt-oss-120b"
CITE_RE = re.compile(r"\[([\w.-]+)@(\d{1,2}):(\d{2})\]")
LABELS = {"search": "searching", "transit": "walking away / fetching", "idle": "idle",
          "hesitation": "hesitation", "extra_reach": "extra reach", "reattempt": "repeated correction",
          "collaboration": "collaboration", "possible_collaboration": "possible collaboration"}


COLLAB = ("collaboration", "possible_collaboration")


def cite(clip_id, t):
    return f"[{clip_id}@{fmt_t(t)}]"


def normalize(text):
    """LLMs sometimes emit typographic hyphens or CJK brackets inside citations; make them parseable."""
    for ch in "‐‑‒–—":
        text = text.replace(ch, "-")
    text = text.replace("【", "[").replace("】", "]").replace(" ", " ")
    # drop an outer bracket pair wrapped around one or more cites: [[a][b]] -> [a][b]
    return re.sub(r"\[\s*((?:\[[\w.-]+@\d{1,2}:\d{2}\][\s,;]*)+)\]", lambda m: m.group(1).strip(), text)


def parse_citations(text):
    return [{"clip_id": c, "t": int(m) * 60 + int(s)} for c, m, s in CITE_RE.findall(text)]


# --------------------------------------------------------------------------- data access (shared)
class Context:
    def __init__(self, clip_ids):
        self.clip_ids = clip_ids
        self.tls = {c: load(c) for c in clip_ids}
        self.report = analyse(clip_ids)

    def events(self, type=None, clip_id=None, limit=20):
        out = []
        for c, tl in self.tls.items():
            if clip_id and c != clip_id:
                continue
            for e in tl["events"]:
                if type and e["type"] != type and not (type == "collaboration" and e["type"] in COLLAB):
                    continue
                out.append({"cite": cite(c, e["t_start"]), "clip_id": c, "t_start": e["t_start"],
                            "duration_s": round(e["t_end"] - e["t_start"], 1), "type": e["type"],
                            "hand": e["hand"], "zone": e["zone"], "tool": e.get("tool"),
                            "step_id": e["step_id"], "note": e["note"]})
        return out[:limit]

    def steps(self, clip_id=None):
        return [{"cite": cite(c, s["t_start"]), "clip_id": c,
                 **{k: s.get(k) for k in ("step_id", "label", "tool", "t_start", "duration_s", "hand", "zone")}}
                for c, tl in self.tls.items() if not clip_id or c == clip_id for s in tl["steps"]]

    def recommendations(self):
        return [{**{k: x[k] for k in ("title", "observation", "action", "confidence", "saving_min_per_shift",
                                      "roi_eur_per_year", "support")},
                 "evidence": [cite(e["clip_id"], e["t"]) for e in x["evidence"][:3]]}
                for x in self.report["recommendations"]]

    def summary(self):
        r = self.report
        return {k: r[k] for k in ("observed_min", "breakdown_pct", "friction", "lost_min_per_shift",
                                  "recoverable_min_per_shift", "roi_eur_per_year_total", "headline")} | {
            "recommendations": self.recommendations()}

    def proficiency(self, clip_id=None, limit=3):
        """Workflow-vs-baseline scores; with no clip, the recordings that deviate most."""
        cache = {}
        clips = [clip_id] if clip_id else self.clip_ids
        rows = []
        for c in clips:
            p = proficiency.score(c, cache)
            worst = [m for m in p["metrics"] if m["direction"] == "worse"]
            rows.append({"clip_id": c, "station": p["station"], "score": p["score"], "level": p["level"],
                         "baseline_recordings": p["baseline_recordings"],
                         "baseline_reliability": p["baseline_reliability"],
                         "deviations": [{"explanation": m["explanation"], "evidence": m["evidence"]} for m in worst]})
        rows.sort(key=lambda x: x["score"] if x["score"] is not None else 100)
        return rows[:limit] if not clip_id else rows

    def skill(self, clip_id=None):
        """Motion skill pattern (expert-like / developing / beginner-like) per recording, learned without labels."""
        cache = {}
        clips = [clip_id] if clip_id else self.clip_ids
        rows = []
        for c in clips:
            s = skill_profile.profile(c, cache)
            rows.append({"clip_id": c, "station": s["station"], "pattern": s["pattern"],
                         "expertise_index": s["expertise_index"], "confidence": s["confidence"],
                         "reliability": s["reliability"], "summary": s["summary"],
                         "evidence": [e for f in s["features"] for e in f["evidence"]][:3]})
        rows.sort(key=lambda x: -x["expertise_index"])
        return rows

    # ---------------------------------------------------------------------- USPs 7-20
    def sop_compliance(self, clip_id, expected_steps, mandatory=None):
        return sop.check(clip_id, expected_steps, mandatory)

    def attention_heatmap(self, clip_id):
        return attention.heatmap(clip_id)

    def search_clips(self, query):
        return factory_search.search(query, self.clip_ids)

    def digital_twin(self, clip_id, shift_start=None):
        return digital_twin.narrate(clip_id, shift_start)

    def safety_risk(self, clip_id=None):
        clips = [clip_id] if clip_id else self.clip_ids
        return [safety.predict(c) for c in clips]

    def collaboration_score(self):
        return collab_score.shift_score(self.clip_ids)

    def behavior_drift(self, clip_id):
        return baseline_drift.drift(clip_id)

    def root_cause_analysis(self):
        return root_cause.analyse(self.clip_ids)

    def knowledge_graph_query(self, question):
        return knowledge_graph.query(question, self.clip_ids)

    def already_done(self, label):
        return memory.already_done(label, self.clip_ids)

    def shift_summary(self):
        return shift_summary.summarize(self.clip_ids)


# --------------------------------------------------------------------------- rules engine
def answer_rules(q, ctx):
    ql = q.lower()
    r = ctx.report

    if any(w in ql for w in ("collaborat", "together", "interact", "help from", "assist")):
        evs = ctx.events(type="collaboration", limit=100)
        if not evs:
            return ("No high-confidence collaboration events were detected in the selected clips. "
                    "Kairo only reports collaboration when several signals agree, so short or unclear "
                    "encounters are left out.")
        evs.sort(key=lambda e: (e["clip_id"], e["t_start"]))
        lines = [f"- {LABELS[e['type']]} {e['duration_s']:.0f}s {cite(e['clip_id'], e['t_start'])}: {e['note']}"
                 for e in evs[:6]]
        return (f"{len(evs)} collaboration event(s), detected from agreeing signals (not from what was said):\n"
                + "\n".join(lines))
    if any(w in ql for w in ("roi", "money", "eur", "euro", "cost", "highest", "biggest", "most value")):
        recs = r["recommendations"]
        if not recs:
            return "No significant friction found, so there is nothing to recommend yet."
        x = recs[0]
        ev = x["evidence"][0] if x["evidence"] else None
        return (f"Highest ROI: **{x['title']}**, about EUR {x['roi_eur_per_year']:,} per station per year "
                f"(~{x['saving_min_per_shift']} min per shift, confidence {round(100 * x['confidence'])}%). "
                f"{x['observation']} Evidence: {x['support']}"
                + (f", e.g. {cite(ev['clip_id'], ev['t'])}." if ev else ".")
                + f" Assumes EUR {r['assumptions']['labor_eur_per_hour']:g}/h; shift figures are extrapolated.")
    if any(w in ql for w in ("expert", "beginner", "novice", "motion", "smooth", "grasp", "cluster",
                             "skill profil", "experienced")):
        rows = ctx.skill()
        groups = {}
        for s in rows:
            groups.setdefault(s["pattern"], []).append(s)
        out = ["Motion skill patterns, learned without labels from how the hands move (compared within each "
               "station; this describes the motion in a recording, not a person):"]
        for pattern in skill_profile.PATTERNS[3]:
            for s in groups.get(pattern, [])[:2 if len(ctx.clip_ids) > 3 else 9]:
                out.append(f"- {s['clip_id']}: {s['pattern']} (index {s['expertise_index']}, "
                           f"{s['reliability']} reliability). {s['summary']} {' '.join(s['evidence'][:2])}".rstrip())
        return "\n".join(out)
    if any(w in ql for w in ("baseline", "deviat", "proficien", "skill", "fingerprint", "normal")):
        rows = ctx.proficiency()
        out = ["Workflow scores against each station's baseline (50 = the station's typical workflow; "
               "this describes the recording, not a person):"]
        for p in rows:
            dev = p["deviations"][0] if p["deviations"] else None
            out.append(f"- {p['clip_id']}: {p['score']} ({p['level']})"
                       + (f". {dev['explanation']} {' '.join(dev['evidence'][:2])}" if dev
                          else ", in line with baseline."))
        return "\n".join(out)

    def ev_lines(typ, n=5, order="time"):
        evs = ctx.events(type=typ, limit=500)
        if order == "longest":
            evs.sort(key=lambda e: -e["duration_s"])
        return [f"- {LABELS.get(e['type'], e['type'])} {e['duration_s']:.1f}s "
                f"{cite(e['clip_id'], e['t_start'])}" + (f" — {e['note']}" if e["note"] else "")
                for e in evs[:n]]

    for typ, words in (("search", ("search", "look for", "find tool", "hunt")),
                       ("transit", ("walk", "transit", "away", "fetch")),
                       ("idle", ("idle", "wait")),
                       ("hesitation", ("hesitat", "stall", "pause")),
                       ("extra_reach", ("reach",)),
                       ("reattempt", ("reattempt", "redo", "retry", "correction", "regrasp"))):
        if any(w in ql for w in words):
            evs = ctx.events(type=typ, limit=500)
            if not evs:
                return f"No {LABELS[typ]} events were detected in the selected clips."
            first = "first" in ql
            last = "last" in ql
            if first or last:
                e = evs[0] if first else evs[-1]
                return (f"The {'first' if first else 'last'} {LABELS[typ]} event was at "
                        f"{cite(e['clip_id'], e['t_start'])}, lasting {e['duration_s']:.1f}s. {e['note'] or ''}")
            tot = sum(e["duration_s"] for e in evs)
            return (f"{len(evs)} {LABELS[typ]} events, {tot:.0f}s in total. Longest:\n"
                    + "\n".join(ev_lines(typ, 5, "longest")))

    if "longest" in ql or "slowest" in ql:
        s = r["longest_step"]
        if s:
            return (f"The longest step is {s['label']} in {s['clip_id']}: {s['duration_s']:.1f}s "
                    f"{cite(s['clip_id'], s['t_start'])}. Average step: {r['avg_step_s']}s.")
    if "step" in ql or "sop" in ql:
        st = ctx.steps()
        lines = [f"- {s['label']} ({s['duration_s']:.0f}s, {s['hand']} hand) {cite(s['clip_id'], s['t_start'])}"
                 for s in st[:12]]
        return f"{len(st)} work steps detected:\n" + "\n".join(lines)
    if any(w in ql for w in ("recommend", "improve", "fix", "sav", "layout", "suggest", "change",
                             "should", "better", "reduce", "optimi")):
        if not r["recommendations"]:
            return "No significant friction found, so there is nothing to recommend yet."
        out = [r["headline"], ""]
        for x in r["recommendations"][:3]:
            ev = x["evidence"][0] if x["evidence"] else None
            out.append(f"- **{x['title']}**: ~{x['saving_min_per_shift']} min/shift. "
                       + (cite(ev["clip_id"], ev["t"]) if ev else ""))
        return "\n".join(out)
    if any(w in ql for w in ("shift report", "shift summary", "end of shift", "today's shift")):
        s = ctx.shift_summary()
        return s["narrative"]
    if any(w in ql for w in ("root cause", "fixture", "defect")):
        causes = ctx.root_cause_analysis()
        if not causes:
            return "No clustered friction pattern matches a known root cause in the selected clips."
        out = []
        for f in causes[:3]:
            out.append(f"- {f['step_label']} ({f['clip_id']}): {f['root_cause']} Fix: {f['fix']} "
                       + " ".join(f["evidence"]))
        return "\n".join(out)
    if any(w in ql for w in ("drift", "deviate significantly", "behaviour chang", "behavior chang",
                             "slower today", "faster today")):
        clip = next((c for c in ctx.clip_ids if c in q), ctx.clip_ids[-1])
        d = ctx.behavior_drift(clip)
        reasons = "; ".join(d.get("possible_reasons", []))
        return d["headline"] + (f" Possible reasons: {reasons}." if reasons else "")
    if any(w in ql for w in ("attention", "heatmap", "looking at", "where was he looking", "gaze")):
        clip = next((c for c in ctx.clip_ids if c in q), ctx.clip_ids[-1])
        hm = ctx.attention_heatmap(clip)
        parts = ", ".join(f"{k} {v}%" for k, v in sorted(hm["pct"].items(), key=lambda kv: -kv[1]) if v > 0)
        return f"Attention breakdown for {clip}: {parts}. Not detected: {', '.join(hm['not_detected'])}."
    if any(w in ql for w in ("safety", "unsafe", "hazard", "risk of injury")):
        rows = ctx.safety_risk()
        configured = [r for r in rows if r["configured"]]
        if not configured:
            return "No unsafe zone is configured for any selected station, so safety risk can't be measured yet."
        forecasts = [f for r in configured for f in r["forecasts"]]
        if not forecasts:
            return "No repeated unsafe reaches detected in the selected clips."
        f = forecasts[0]
        return f["note"] + f" {f['cite']}"
    if "tool" in ql and "delay" in ql:
        return ctx.knowledge_graph_query(q)["answer"]
    if "delay" in ql and ("task" in ql or "step" in ql or "causes" in ql):
        return ctx.knowledge_graph_query(q)["answer"]
    if any(w in ql for w in ("show clips where", "find every instance", "find clips", "search for")):
        hits = ctx.search_clips(q)
        if not hits["hits"]:
            return "No matching clips/events found."
        lines = [f"- {h['cite']}: {h['note']}" for h in hits["hits"][:8]]
        out = f"{hits['count']} match(es):\n" + "\n".join(lines)
        if hits["proxy_notes"]:
            out += "\n" + "\n".join(hits["proxy_notes"])
        return out
    if "already" in ql and ("done" in ql or "completed" in ql or "finished" in ql):
        m = (re.search(r"^(?:has|have|is|was|did)\s+(.+?)\s+(?:already\s+)?(?:been\s+)?"
                       r"(?:done|completed|finished)\b", ql)
             or re.search(r"(?:done|completed|finished)\s+(.+?)[?.]?$", ql))
        label = m.group(1) if m else q
        return ctx.already_done(label)["note"]
    if any(w in ql for w in ("who blocks", "waiting time", "dependency", "communication")):
        cs = ctx.collaboration_score()
        return (f"{cs['total_collaboration_events']} collaboration events across the selected clips, "
                f"{cs['total_waiting_s']:.0f}s total waiting on another person. "
                + (f"Most waiting: {cs['clip_with_most_waiting']}." if cs["clip_with_most_waiting"] else "")
                + f" {cs['note']}")
    if any(w in ql for w in ("why", "ineffici", "waste", "lost", "breakdown", "summary", "how")):
        b = r["breakdown_pct"]
        parts = ", ".join(f"{LABELS.get(k, k)} {v}%" for k, v in sorted(b.items(), key=lambda kv: -kv[1]))
        top = r["recommendations"][0] if r["recommendations"] else None
        return (f"Time split over {r['observed_min']} min: {parts}. Friction costs about "
                f"{r['lost_min_per_shift']} min per {r['shift_hours']:g}h shift (extrapolated)."
                + (f"\nBiggest lever: {top['title']} (~{top['saving_min_per_shift']} min/shift), e.g. "
                   f"{cite(top['evidence'][0]['clip_id'], top['evidence'][0]['t'])}." if top and top["evidence"] else ""))
    return ("I answer from the event timeline. Try: \"Where was time lost?\", "
            "\"Which recommendation has the highest ROI?\", \"Did the workflow deviate from baseline?\", "
            "\"When did collaboration occur?\", \"Which step took the longest?\", \"Give me the shift summary\", "
            "\"What's the likely root cause?\", \"Did behaviour drift today?\", \"Which task causes the most "
            "delay?\"")


# --------------------------------------------------------------------------- claude engine
TOOLS = [
    {"name": "get_summary", "description": "Time breakdown, friction totals, lost minutes per shift and ranked "
     "recommendations for the selected clips.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_events", "description": "Timeline events. type is one of search, transit, idle, hesitation, "
     "extra_reach, reattempt, collaboration, possible_collaboration (omit for all). Times are seconds from clip "
     "start.",
     "input_schema": {"type": "object", "properties": {
         "type": {"type": ["string", "null"]}, "clip_id": {"type": ["string", "null"]},
         "limit": {"type": ["integer", "null"]}}}},
    {"name": "list_steps", "description": "Detected work steps (SOP candidates) with start/end and duration.",
     "input_schema": {"type": "object", "properties": {"clip_id": {"type": ["string", "null"]}}}},
    {"name": "get_recommendations", "description": "Ranked recommendations with observation, confidence, minutes "
     "per shift, EUR per year (ROI) and evidence cites.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_proficiency", "description": "Workflow score (0-100, 50 = station baseline) with explained "
     "deviations and evidence cites. Omit clip_id for the recordings that deviate most. Describes workflows, "
     "never people.", "input_schema": {"type": "object", "properties": {"clip_id": {"type": ["string", "null"]}}}},
    {"name": "get_skill_profile", "description": "Motion skill pattern per recording (Expert-like, Developing, "
     "Beginner-like), clustered without labels from hand-motion features: smoothness, speed, corrections, "
     "repeated grasps, motion entropy, idle time, looking around. Index 50 = the station's typical motion. "
     "Describes the motion in a recording, never a person. Omit clip_id for all selected recordings.",
     "input_schema": {"type": "object", "properties": {"clip_id": {"type": ["string", "null"]}}}},
    {"name": "check_sop_compliance", "description": "Compare one clip's detected steps against a written SOP "
     "(an ordered list of expected step names). Reports missing steps, out-of-order steps, extra steps, and "
     "any skipped mandatory step (e.g. an inspection).",
     "input_schema": {"type": "object", "properties": {
         "clip_id": {"type": "string"}, "expected_steps": {"type": "array", "items": {"type": "string"}},
         "mandatory": {"type": ["array", "null"], "items": {"type": "string"}}},
         "required": ["clip_id", "expected_steps"]}},
    {"name": "get_attention_heatmap", "description": "Share of time the head-mounted camera pointed at the "
     "machine/work, each tool-search zone, a colleague (collaboration signal), or was idle/away. No phone "
     "zone: there is no object detector for one in this stack.",
     "input_schema": {"type": "object", "properties": {"clip_id": {"type": "string"}}, "required": ["clip_id"]}},
    {"name": "search_clips", "description": "Natural-language search over all selected clips' steps and "
     "friction events, returning timestamped hits. Keyword-routed, not a trained NLP model; queries with no "
     "real detector behind them (e.g. 'dropped', 'asked for help') return the closest measured proxy and say "
     "so in proxy_notes.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_digital_twin", "description": "A chronological, narrated timeline for one clip (steps, "
     "conversations, idle spells) -- a digital-twin view of the station's activity. shift_start ('HH:MM') "
     "adds wall-clock labels; omit it to keep relative mm:ss only.",
     "input_schema": {"type": "object", "properties": {
         "clip_id": {"type": "string"}, "shift_start": {"type": ["string", "null"]}}, "required": ["clip_id"]}},
    {"name": "get_safety_risk", "description": "Unsafe-reach events and a frequency-based forecast of another "
     "one soon, for stations with an unsafe zone configured. Returns 'configured': false (and no events) for "
     "a station nobody has configured a danger zone for -- that is not the same as 'safe'.",
     "input_schema": {"type": "object", "properties": {"clip_id": {"type": ["string", "null"]}}}},
    {"name": "get_collaboration_score", "description": "Help frequency, waiting time, dependency and "
     "communication share, aggregated from collaboration events across the selected clips. Never ranks a "
     "worker; scores recordings, since Kairo tracks no worker identity.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_behavior_drift", "description": "Compares one clip with its OWN station's recent history "
     "(self baseline, not a cross-worker ranking). Flags a significant change and, if one exists, which "
     "friction type grew the most, with plausible (never asserted) reasons.",
     "input_schema": {"type": "object", "properties": {"clip_id": {"type": "string"}}, "required": ["clip_id"]}},
    {"name": "get_root_cause_analysis", "description": "Matches clustered friction patterns (e.g. repeated "
     "re-grasps + extra reach on one step) to a plausible mechanical root cause and fix, with evidence cites. "
     "Deterministic rules, not an LLM guess.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "query_knowledge_graph", "description": "Ask which task or friction type causes the highest "
     "measured delay across the selected clips. A 'tool' question returns a message saying no tool detector "
     "exists yet, rather than an invented number.",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"}},
      "required": ["question"]}},
    {"name": "check_already_done", "description": "Was a step matching this label already completed earlier "
     "in the selected clips (treated as one shift, in the given order)? Guards against re-reporting the same "
     "completed work.",
     "input_schema": {"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"]}},
    {"name": "get_shift_summary", "description": "An end-of-shift report: clips processed, average active "
     "work time, collaboration events, probable safety events, the most common friction, a root-cause "
     "finding and the top recommendation. Says plainly when a section (quality deviations, safety) needs a "
     "capability not yet configured for this site.",
     "input_schema": {"type": "object", "properties": {}}},
]

SYSTEM = """You are Kairo, a process-improvement copilot for factory egocentric video.
You evaluate the workstation and process, never the worker as a person: say "the workflow deviates from
the baseline", never "the worker is slow". Skill patterns describe the motion in a recording ("this
recording shows expert-like motion"), never a person. Collaboration events come from agreeing signals; never claim
what people said.
Answer only from tool results. If the data does not contain the answer, say so. There is no tool
detector, phone detector or worker identity in this stack: if a tool result says a capability isn't
configured or detected (e.g. no unsafe zone, no SOP template, no tool node), repeat that limitation
instead of guessing a number.
Every event, step and recommendation in the tool results has a "cite" string like
[MTL-SGF00106-021@00:46]. When you mention a moment, paste its cite string exactly as given (plain
ASCII square brackets and hyphens) - the UI turns it into a video link. Do not write times any other way.
Cite at most 4 moments. Keep answers short: 1-4 sentences or a short list. Shift figures are
extrapolations; say so when you quote them."""


def _run_tool(ctx, name, args):
    if name == "get_summary":
        return ctx.summary()
    if name == "list_events":
        return ctx.events(args.get("type"), args.get("clip_id"), args.get("limit") or 20)
    if name == "list_steps":
        return ctx.steps(args.get("clip_id"))
    if name == "get_recommendations":
        return ctx.recommendations()
    if name == "get_proficiency":
        return ctx.proficiency(args.get("clip_id"))
    if name == "get_skill_profile":
        return ctx.skill(args.get("clip_id"))
    if name == "check_sop_compliance":
        return ctx.sop_compliance(args["clip_id"], args["expected_steps"], args.get("mandatory"))
    if name == "get_attention_heatmap":
        return ctx.attention_heatmap(args["clip_id"])
    if name == "search_clips":
        return ctx.search_clips(args["query"])
    if name == "get_digital_twin":
        return ctx.digital_twin(args["clip_id"], args.get("shift_start"))
    if name == "get_safety_risk":
        return ctx.safety_risk(args.get("clip_id"))
    if name == "get_collaboration_score":
        return ctx.collaboration_score()
    if name == "get_behavior_drift":
        return ctx.behavior_drift(args["clip_id"])
    if name == "get_root_cause_analysis":
        return ctx.root_cause_analysis()
    if name == "query_knowledge_graph":
        return ctx.knowledge_graph_query(args["question"])
    if name == "check_already_done":
        return ctx.already_done(args["label"])
    if name == "get_shift_summary":
        return ctx.shift_summary()
    return {"error": f"unknown tool {name}"}


def answer_claude(q, ctx, history=None):
    import anthropic

    client = anthropic.Anthropic()
    messages = list(history or []) + [{"role": "user", "content": f"Clips: {ctx.clip_ids}\n\n{q}"}]
    for _ in range(6):
        resp = client.beta.messages.create(
            model=MODEL, max_tokens=4000, system=SYSTEM, tools=TOOLS, messages=messages,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            return "I can't answer that one."
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                out = _run_tool(ctx, b.name, b.input if isinstance(b.input, dict) else {})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
        messages.append({"role": "user", "content": results})
    return "I couldn't finish that answer."


def answer_groq(q, ctx):
    from groq import Groq

    client = Groq(max_retries=4, timeout=60)
    tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                               "parameters": t["input_schema"]}} for t in TOOLS]
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Clips: {ctx.clip_ids}\n\n{q}"}]
    for _ in range(6):
        resp = client.chat.completions.create(model=GROQ_MODEL, messages=messages, tools=tools,
                                              tool_choice="auto", max_tokens=2000)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in msg.tool_calls]})
        for c in msg.tool_calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            messages.append({"role": "tool", "tool_call_id": c.id,
                             "content": json.dumps(_run_tool(ctx, c.function.name, args))})
    return None


def groq_available():
    try:
        import groq  # noqa: F401
        return bool(os.environ.get("GROQ_API_KEY"))
    except ImportError:
        return False


def claude_available():
    try:
        import anthropic  # noqa: F401
        anthropic.Anthropic()  # raises if no credentials can be resolved
        return True
    except Exception:
        return False


def available_engines():
    """LLM engines with credentials, in fallback order (rules is implicit and always last)."""
    return [name for name, ok in (("groq", groq_available), ("claude", claude_available)) if ok()]


def available_engine():
    return (available_engines() or ["rules"])[0]


def ask(question, clip_ids, engine="auto"):
    ctx = Context(clip_ids)
    used = "rules"
    text = None
    order = {"auto": available_engines(), "groq": ["groq"], "claude": ["claude"]}.get(engine, [])
    for name in order:
        try:
            text = answer_groq(question, ctx) if name == "groq" else answer_claude(question, ctx)
        except Exception as e:  # network / auth / rate limit -> next engine, then deterministic rules
            text = None
            print(f"{name} engine failed: {type(e).__name__}: {e}", file=sys.stderr)
        if text:
            used = name
            break
    if not text:
        text, used = answer_rules(question, ctx), "rules"
    text = normalize(text)
    return {"answer": text, "citations": parse_citations(text), "engine": used}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--engine", default="auto", choices=["auto", "rules", "groq", "claude"])
    a = ap.parse_args()
    print(json.dumps(ask(a.question, a.clips, a.engine), indent=1))
