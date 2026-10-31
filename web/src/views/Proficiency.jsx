import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Dial, Radar } from "../ui.jsx";
import { Rich } from "./Copilot.jsx";

const LEVEL_CLASS = { Advanced: "ok", Intermediate: "warn", "Needs training": "bad" };

export default function Proficiency({ clip, seek, setClip }) {
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setP(null); setErr(null);
    api.proficiency(clip).then(setP).catch((e) => setErr(e.message));
  }, [clip]);
  if (err) return <div className="error">{err}</div>;
  if (!p) return <div className="boot-inline">Comparing this workflow with the station baseline…</div>;
  const maxCurve = 100;
  return (
    <div className="prof">
      <div className="cmp-h">
        <div>
          <h2>Workflow proficiency · {clip}</h2>
          <p className="muted">
            Compared with {p.baseline_recordings} other recording{p.baseline_recordings === 1 ? "" : "s"} of {p.baseline_scope === "station" ? `station ${p.station}` : "all stations"}
            {" "}(baseline reliability: <b>{p.baseline_reliability}</b>). {p.level_note}
          </p>
        </div>
      </div>

      <div className="prof-top">
        <div className="panel glass prof-score">
          <Dial value={p.score} label="workflow score" />
          <span className={"pill " + LEVEL_CLASS[p.level]}>{p.level}</span>
          <p className="muted small">50 = the station's typical workflow. ≥{p.thresholds.advanced} Advanced, &lt;{p.thresholds.needs_training} Needs training.</p>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Skill fingerprint</h3><span className="muted">outer = better than baseline · ring = baseline</span></div>
          <Radar data={p.fingerprint} />
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Score across recordings</h3><span className="muted">{p.station}</span></div>
          <div className="curve">
            {p.curve.map((c) => (
              <button key={c.clip_id} className={"cbar" + (c.clip_id === clip ? " on" : "")} title={`${c.clip_id}: ${c.score}`}
                      onClick={() => setClip(c.clip_id)}>
                <i style={{ height: `${(100 * (c.score ?? 0)) / maxCurve}%` }} />
                <span>{c.clip_id.slice(-3)}</span>
              </button>
            ))}
          </div>
          <p className="muted small">Recordings in order. If they are sequential sessions, this is a learning curve.</p>
        </div>
      </div>

      <h3 className="sec">Why this score</h3>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Metric</th><th>This workflow</th><th>Baseline</th><th>Sub-score</th><th>Explanation and evidence</th></tr></thead>
          <tbody>
            {p.metrics.map((m) => (
              <tr key={m.metric}>
                <td>{m.label}</td>
                <td className="num">{m.value}{m.unit}</td>
                <td className="num muted">{m.baseline}{m.unit}</td>
                <td><span className={"pill " + (m.direction === "better" ? "ok" : m.direction === "worse" ? "bad" : "warn")}>{m.subscore}</span></td>
                <td><Rich text={m.explanation + (m.evidence.length ? " " + m.evidence.join(" ") : "")} seek={seek} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">{p.method} Collaboration in this recording: {p.context.collaboration_s_per_min} s/min (context only, not scored).</p>
    </div>
  );
}
