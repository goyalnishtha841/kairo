"""Industrial Knowledge Graph (USP 19): link station, task (step), tool, friction, collaboration and
safety data across clips into queryable nodes and edges, so a supervisor can ask "which X causes the
highest delay?" over the whole dataset instead of one clip at a time.

Honesty note: a tool node only appears for a clip whose station has perception/tools.py's open-
vocabulary detector configured (events/config.py STATION_TOOLS) -- and even then, those detections
are unvalidated (no labelled footage exists to measure precision/recall against; see
perception/tools.py). Without a configured detector, a "which tool...?" query says so plainly instead
of returning an invented number; with one, the answer is a real (if unvalidated) measurement, not a
guess, and is labelled as such.

Usage: python events/knowledge_graph.py "which task causes the highest delay?" <clip_id> [<clip_id> ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t, load  # noqa: E402
from proficiency import station_of  # noqa: E402
import safety  # noqa: E402

NO_TOOL_NOTE = ("No tool node: no station in the selected clips has tool detection configured "
                "(events/config.py STATION_TOOLS), so tool-delay questions can't be answered from real "
                "evidence yet.")
TOOL_UNVALIDATED_NOTE = ("Based on unvalidated open-vocabulary tool detection (perception/tools.py): "
                         "no labelled footage exists to measure its precision/recall.")


def _clip_ids():
    return sorted(p.parent.name for p in OUT.glob("*/timeline.json") if not p.parent.name.startswith("zz-"))


def build(clip_ids=None):
    """A simple node/edge graph: Station -[recorded]-> Clip -[performed]-> Task -[showed]-> Friction."""
    clip_ids = clip_ids or _clip_ids()
    nodes, edges = {}, []

    def node(kind, key, **attrs):
        nid = f"{kind}:{key}"
        nodes.setdefault(nid, {"id": nid, "kind": kind, "key": key, **attrs})
        return nid

    for c in clip_ids:
        tl = load(c)
        st_id = node("station", station_of(c))
        clip_nid = node("clip", c, station=station_of(c))
        edges.append({"from": st_id, "to": clip_nid, "rel": "recorded"})
        for s in tl["steps"]:
            task_id = node("task", s["label"])
            edges.append({"from": clip_nid, "to": task_id, "rel": "performed",
                          "duration_s": s["duration_s"], "cite": f"[{c}@{fmt_t(s['t_start'])}]"})
            if s.get("tool_detected"):
                tool_id = node("tool", s["tool_detected"], validated=False)
                edges.append({"from": task_id, "to": tool_id, "rel": "uses",
                              "confidence": s.get("tool_detected_confidence"),
                              "cite": f"[{c}@{fmt_t(s['t_start'])}]"})
        for e in tl["events"]:
            if e["type"] in ("collaboration", "possible_collaboration"):
                edges.append({"from": clip_nid, "to": node("collaboration", "event"), "rel": "had",
                              "cite": f"[{c}@{fmt_t(e['t_start'])}]"})
                continue
            if e["severity"] == "green":
                continue
            step = next((s for s in tl["steps"] if s["step_id"] == e["step_id"]), None)
            if step:
                fric_id = node("friction", e["type"])
                edges.append({"from": node("task", step["label"]), "to": fric_id, "rel": "showed",
                              "duration_s": round(e["t_end"] - e["t_start"], 1),
                              "tool": step.get("tool_detected"), "cite": f"[{c}@{fmt_t(e['t_start'])}]"})
        risk = safety.predict(c)
        for f in risk.get("forecasts", []):
            edges.append({"from": clip_nid, "to": node("safety_risk", "forecast"), "rel": "had",
                          "cite": f["cite"], "probability": f["probability_next_window"]})

    tool_nodes = sum(1 for n in nodes.values() if n["kind"] == "tool")
    return {"nodes": list(nodes.values()), "edges": edges, "clip_ids": clip_ids,
            "tool_nodes": tool_nodes, "note": NO_TOOL_NOTE if not tool_nodes else TOOL_UNVALIDATED_NOTE}


def delay_by(graph, dim="task"):
    """Total seconds of friction ('showed' edges), summed by task, friction type, or (when any clip
    had tool detection configured) tool. Returns [] honestly for dim='tool' when no tool node exists."""
    id_to_node = {n["id"]: n for n in graph["nodes"]}
    totals = {}
    for e in graph["edges"]:
        if e["rel"] != "showed":
            continue
        if dim == "tool":
            if not e.get("tool"):
                continue
            key = f"tool:{e['tool']}"
        else:
            key = e["from"] if dim == "task" else e["to"]
        totals[key] = totals.get(key, 0.0) + e.get("duration_s", 0.0)
    rows = []
    for k, v in totals.items():
        if dim == "tool":
            label, kind = k.split(":", 1)[1], "tool"
        else:
            label, kind = id_to_node[k]["key"], id_to_node[k]["kind"]
        rows.append({"key": label, "kind": kind, "total_delay_s": round(v, 1)})
    rows.sort(key=lambda r: -r["total_delay_s"])
    return rows


def query(question, clip_ids=None):
    graph = build(clip_ids)
    ql = question.lower()
    if "tool" in ql:
        if not graph["tool_nodes"]:
            return {"answer": graph["note"], "rows": []}
        rows = delay_by(graph, "tool")
        if not rows:
            return {"answer": "Tool detection is configured, but no detected tool overlapped a friction "
                              "event in the selected clips.", "rows": []}
        top = rows[0]
        return {"answer": f"'{top['key']}' is associated with the highest measured delay: "
                          f"{top['total_delay_s']:.0f}s across the selected clips. {TOOL_UNVALIDATED_NOTE}",
               "rows": rows[:10]}
    dim = "friction" if ("friction" in ql or "type" in ql) else "task"
    rows = delay_by(graph, dim)
    if not rows:
        return {"answer": "No friction evidence in the selected clips.", "rows": []}
    top = rows[0]
    return {"answer": f"'{top['key']}' causes the highest measured delay: {top['total_delay_s']:.0f}s across "
                      f"the selected clips.", "rows": rows[:10]}


if __name__ == "__main__":
    print(json.dumps(query(sys.argv[1], sys.argv[2:] or None), indent=1))
