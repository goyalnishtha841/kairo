"""Industrial Knowledge Graph (USP 19): link station, task (step), friction, collaboration and safety
data across clips into queryable nodes and edges, so a supervisor can ask "which X causes the highest
delay?" over the whole dataset instead of one clip at a time.

Honesty note: there is no tool detector in this stack yet (docs/STRATEGY.md -- "tool pick/release
events" is a roadmap item, and claiming it would misrepresent the product; every event's `tool` field
is null today). The graph still works over the signals Kairo DOES have (station, task/step, friction
type, collaboration, safety when configured); a tool query says plainly that it isn't answerable yet
instead of returning an invented number.

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

NO_TOOL_NOTE = ("No tool node: no tool detector exists in this stack yet (docs/STRATEGY.md roadmap), so "
                "tool-delay questions can't be answered from real evidence today.")


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
        for e in tl["events"]:
            if e["type"] in ("collaboration", "possible_collaboration"):
                edges.append({"from": clip_nid, "to": node("collaboration", "event"), "rel": "had",
                              "cite": f"[{c}@{fmt_t(e['t_start'])}]"})
                continue
            if e["severity"] == "green":
                continue
            task_label = next((s["label"] for s in tl["steps"] if s["step_id"] == e["step_id"]), None)
            if task_label:
                fric_id = node("friction", e["type"])
                edges.append({"from": node("task", task_label), "to": fric_id, "rel": "showed",
                              "duration_s": round(e["t_end"] - e["t_start"], 1),
                              "cite": f"[{c}@{fmt_t(e['t_start'])}]"})
        risk = safety.predict(c)
        for f in risk.get("forecasts", []):
            edges.append({"from": clip_nid, "to": node("safety_risk", "forecast"), "rel": "had",
                          "cite": f["cite"], "probability": f["probability_next_window"]})

    return {"nodes": list(nodes.values()), "edges": edges, "clip_ids": clip_ids,
            "tool_nodes": 0, "note": NO_TOOL_NOTE}


def delay_by(graph, dim="task"):
    """Total seconds of friction ('showed' edges), summed by task or friction type. Returns [] honestly
    for dim='tool' since no tool node exists yet."""
    if dim == "tool":
        return []
    id_to_node = {n["id"]: n for n in graph["nodes"]}
    totals = {}
    for e in graph["edges"]:
        if e["rel"] != "showed":
            continue
        key = e["from"] if dim == "task" else e["to"]
        totals[key] = totals.get(key, 0.0) + e.get("duration_s", 0.0)
    rows = [{"key": id_to_node[k]["key"], "kind": id_to_node[k]["kind"], "total_delay_s": round(v, 1)}
            for k, v in totals.items()]
    rows.sort(key=lambda r: -r["total_delay_s"])
    return rows


def query(question, clip_ids=None):
    graph = build(clip_ids)
    ql = question.lower()
    if "tool" in ql:
        return {"answer": graph["note"], "rows": []}
    dim = "friction" if ("friction" in ql or "type" in ql) else "task"
    rows = delay_by(graph, dim)
    if not rows:
        return {"answer": "No friction evidence in the selected clips.", "rows": []}
    top = rows[0]
    return {"answer": f"'{top['key']}' causes the highest measured delay: {top['total_delay_s']:.0f}s across "
                      f"the selected clips.", "rows": rows[:10]}


if __name__ == "__main__":
    print(json.dumps(query(sys.argv[1], sys.argv[2:] or None), indent=1))
