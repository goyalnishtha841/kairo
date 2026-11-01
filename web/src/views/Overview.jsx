import React, { useEffect, useState } from "react";
import { api, LABEL } from "../api.js";
import { Rich } from "./Copilot.jsx";

// "137 min" -> "2 h 17 min"; small values stay in minutes
export const mins = (m) => {
  const v = Math.round(m || 0);
  return v < 60 ? `${v} min` : `${Math.floor(v / 60)} h${v % 60 ? ` ${v % 60} min` : ""}`;
};

// root-cause patterns (events/root_cause.py), said simply
export const CAUSE = {
  loose_fixture: ["The part keeps being moved around the same spot", "The holder or jig for the part may be loose or missing.",
    "Check or add the holder that keeps the part still."],
  missing_tool_station: ["The same tool is searched for again and again", "The tool probably isn't kept at the station, or there aren't enough.",
    "Give that tool a fixed place within arm's reach, or add a second one."],
  unclear_reference: ["Hands pause before placing a part", "There is no clear mark for where the part should go.",
    "Add a stop, guide or marked position."],
};

const GO = [
  ["analyze", "Watch a video", "See every second labelled."],
  ["impact", "Fixes & safety", "Every fix and the proof behind it."],
  ["search", "Search", "Ask in plain words, jump to the moment."],
  ["report", "Report", "Everything in one page, plus a PDF."],
];

function story(r, s) {
  const work = Math.round(r.breakdown_pct.work ?? 0);
  const top = r.recommendations[0];
  const common = s && s.most_common_friction;
  const parts = [`Across ${r.clips.length} videos (${Math.round(r.observed_min)} minutes), hands were on the work ${work}% of the time.`];
  if (common) parts.push(`The biggest time-waster was ${(LABEL[common.type] || common.type).toLowerCase()}: ${common.count} times, about ${mins(common.seconds / 60)} in total.`);
  if (top) parts.push(`Fix first: ${top.title.toLowerCase()}. It would save about ${Math.round(top.saving_min_per_shift)} minutes every shift.`);
  return parts.join(" ");
}

export default function Overview({ report: r, seek, go }) {
  const [summary, setSummary] = useState(null);
  const [causes, setCauses] = useState(null);
  useEffect(() => { api.shiftSummary(r.clips).then(setSummary).catch(() => setSummary(false)); }, [r.clips]);
  useEffect(() => { api.rootCause(r.clips).then(setCauses).catch(() => setCauses([])); }, [r.clips]);
  const common = summary && summary.most_common_friction;
  const lostPct = Math.round((100 * r.lost_min_per_shift) / (60 * r.shift_hours));
  // one entry per kind of cause, with every place it was seen
  const grouped = (causes || []).reduce((g, c) => { (g[c.pattern] ||= []).push(c); return g; }, {});
  return (
    <div className="overview">
      <div className="ov-hero">
        <div className="ov-story">
          <div>
            <span className="ai-tag">IN SHORT</span>
            <p>{summary === null ? "Reading the shift…" : story(r, summary)}</p>
          </div>
          <small>Per-shift numbers are scaled up from the video watched to an {r.shift_hours}-hour shift.</small>
        </div>
        <div className="ov-big">
          <div className="tile"><span>Time lost per shift</span><b style={{ color: "var(--red)" }}>{mins(r.lost_min_per_shift)}</b><small>{lostPct}% of an {r.shift_hours}-hour shift</small></div>
          <div className="tile"><span>Time you can win back</span><b style={{ color: "var(--accent-ink)" }}>{mins(r.recoverable_min_per_shift)}</b><small>per shift, with the fixes below</small></div>
          <div className="tile"><span>Hands on the work</span><b>{Math.round(r.breakdown_pct.work ?? 0)}%</b><small>of the time on camera</small></div>
          <div className="tile"><span>Biggest time-waster</span><b>{common ? LABEL[common.type] || common.type : "–"}</b>
            <small>{common ? `${common.count} times` : ""}</small></div>
        </div>
      </div>

      <div className="ov-grid">
        <div className="panel">
          <div className="panel-h"><h3>Fix these first</h3><button className="ghost sm" onClick={() => go("impact")}>All fixes →</button></div>
          {r.recommendations.slice(0, 3).map((x, i) => {
            const ev = x.evidence && x.evidence[0];
            return (
              <div key={x.title} className="ov-fix">
                <span className="n">{i + 1}</span>
                <div>
                  <b>{x.title}</b>
                  <div className="muted small">Seen {x.evidence_stats?.events ?? ""} times in {x.evidence_stats?.clips ?? "?"} of {x.evidence_stats?.of_clips ?? r.clips.length} videos
                    {ev && <> · <a className="cite" onClick={() => seek(ev.clip_id, ev.t)}>▶ see it</a></>}</div>
                </div>
                <span className="save">~{Math.round(x.saving_min_per_shift)} min<small>saved per shift</small></span>
              </div>
            );
          })}
          {!r.recommendations.length && <p className="muted pad">No real time loss found yet.</p>}
        </div>
        <div className="panel">
          <div className="panel-h"><h3>Why it happens</h3><span className="muted small">from repeated patterns</span></div>
          {causes === null ? <p className="muted pad">Looking for patterns…</p>
            : !Object.keys(grouped).length ? <p className="muted pad">No repeated pattern points to a clear cause yet.</p>
              : Object.entries(grouped).slice(0, 3).map(([pattern, list]) => {
                const [what, why, fix] = CAUSE[pattern] || [list[0].step_label, list[0].root_cause, list[0].fix];
                const ev = list.flatMap((c) => c.evidence.slice(0, 1)).slice(0, 3).join(" ");
                return (
                  <div key={pattern} className="ov-cause">
                    <b>{what}</b> <span className="muted small">· in {list.length} video{list.length === 1 ? "" : "s"}</span>
                    <div>{why} <Rich text={ev} seek={seek} /></div>
                    <div className="muted small">Try: {fix}</div>
                  </div>
                );
              })}
        </div>
      </div>

      <div className="ov-go">
        {GO.map(([k, h, p]) => (
          <button key={k} onClick={() => go(k)}><b>{h}</b><span>{p}</span><span className="arrow">Open →</span></button>
        ))}
      </div>
      <p className="muted small" style={{ marginTop: 18 }}>Kairo looks at workstations and how the job flows, never at who did it.</p>
    </div>
  );
}
