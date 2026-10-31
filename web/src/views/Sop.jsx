import React from "react";
import { api, fmt } from "../api.js";

export default function Sop({ clip, timeline, seek }) {
  const steps = timeline.steps;
  const total = steps.reduce((a, s) => a + s.duration_s, 0);
  const evBy = (sid) => timeline.events.filter((e) => e.step_id === sid && e.severity !== "green");
  return (
    <div className="sop">
      <div className="sop-h">
        <div>
          <h2>Standard Work: {clip}</h2>
          <p className="muted">
            Generated automatically from hand-object activity: {steps.length} steps, {total.toFixed(0)}s of hands-on work.
            Use the cleanest clip as the reference SOP and compare other clips against it.
          </p>
        </div>
        <button className="ghost" onClick={() => window.print()}>Print SOP</button>
      </div>
      <div className="steps">
        {steps.map((s) => {
          const fr = evBy(s.step_id);
          return (
            <div key={s.step_id} className="step" onClick={() => seek(clip, s.t_start)}>
              <div className="thumb">
                {s.keyframe ? <img src={api.frame(clip, s.keyframe)} alt="" loading="lazy" /> : <div className="noimg" />}
                <span className="num">{s.step_id}</span>
                <span className="dur">{s.duration_s.toFixed(1)}s</span>
              </div>
              <div className="step-b">
                <b>{s.label}</b>
                <div className="meta">
                  <span>{fmt(s.t_start)}–{fmt(s.t_end)}</span>
                  <span>{s.hand === "both" ? "Both hands" : s.hand === "L" ? "Left hand" : "Right hand"}</span>
                  {s.tool && <span>Tool: {s.tool}</span>}
                  {s.zone && <span>Zone: {s.zone}</span>}
                  <span>Active {Math.round(s.active_ratio * 100)}%</span>
                </div>
                {fr.length > 0 && <div className="warn">⚠ {fr.length} friction event{fr.length > 1 ? "s" : ""} in this step</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
