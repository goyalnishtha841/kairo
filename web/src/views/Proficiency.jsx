import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Dial, Radar } from "../ui.jsx";
import { Rich } from "./Copilot.jsx";

const LEVEL_CLASS = { Advanced: "ok", Intermediate: "warn", "Needs training": "bad" };
// the backend's levels describe the workflow; say so plainly (never "needs training", which sounds like the person)
const LEVEL_TEXT = { Advanced: "Better than usual", Intermediate: "About usual", "Needs training": "Below usual" };

function Drift({ clip }) {
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api.drift(clip).then(setD).catch(() => {}); }, [clip]);
  if (!d) return null;
  return (
    <>
      <h3 className="sec">Is it changing over time?</h3>
      <div className="panel glass pad">
        {d.prior_clips.length === 0 ? (
          <p className="muted small">{d.headline}</p>
        ) : (
          <>
            <p>
              <span className={"pill " + (d.drifted ? (d.change_pct < 0 ? "bad" : "ok") : "warn")}>
                {d.change_pct > 0 ? "+" : ""}{d.change_pct}%
              </span>{" "}{d.headline}
            </p>
            <p className="muted small">
              {Math.round(d.today_active_work_s)} s of active work, against a usual {Math.round(d.baseline_active_work_s)} s
              {" "}from {d.prior_clips.length} earlier video{d.prior_clips.length > 1 ? "s" : ""} at this station.
            </p>
            {d.drifted && d.possible_reasons.length > 0 && (
              <ul className="replist">
                {d.possible_reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            )}
          </>
        )}
      </div>
    </>
  );
}

export default function Proficiency({ clip, seek, setClip }) {
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setP(null); setErr(null);
    api.proficiency(clip).then(setP).catch((e) => setErr(e.message));
  }, [clip]);
  if (err) return <div className="error">{err}</div>;
  if (!p) return <div className="boot-inline">Comparing with how this station usually runs…</div>;
  const maxCurve = 100;
  return (
    <div className="prof">
      <div className="cmp-h">
        <div>
          <h2>Workflow proficiency · {clip}</h2>
          <p className="muted">
            Compared with {p.baseline_recordings} other video{p.baseline_recordings === 1 ? "" : "s"} from {p.baseline_scope === "station" ? "this station" : "all stations"}. It describes the video, not the person.
          </p>
        </div>
      </div>

      <div className="prof-top">
        <div className="panel glass prof-score">
          <Dial value={p.score} label="score vs usual" />
          <span className={"pill " + LEVEL_CLASS[p.level]}>{LEVEL_TEXT[p.level] || p.level}</span>
          <p className="muted small">50 means usual for this station. Higher is better.</p>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Better or worse than usual</h3><span className="muted">outside the ring = better</span></div>
          <Radar data={p.fingerprint} />
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Every video at this station</h3><span className="muted">{p.station}</span></div>
          <div className="curve">
            {p.curve.map((c) => (
              <button key={c.clip_id} className={"cbar" + (c.clip_id === clip ? " on" : "")} title={`${c.clip_id}: ${c.score}`}
                      onClick={() => setClip(c.clip_id)}>
                <i style={{ height: `${(100 * (c.score ?? 0)) / maxCurve}%` }} />
                <span>{c.clip_id.slice(-3)}</span>
              </button>
            ))}
          </div>
          <p className="muted small" style={{ padding: "0 18px 14px" }}>In recording order. Click a bar to open that video.</p>
        </div>
      </div>

      <h3 className="sec">What makes up the score</h3>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>What</th><th>This video</th><th>Usual</th><th>Score</th><th>Why, with moments to watch</th></tr></thead>
          <tbody>
            {p.metrics.map((m) => (
              <tr key={m.metric}>
                <td>{m.label}</td>
                <td className="num">{m.value}{m.unit}</td>
                <td className="num muted">{m.baseline}{m.unit}</td>
                <td><span className={"pill " + (m.direction === "better" ? "ok" : m.direction === "worse" ? "bad" : "warn")}>{m.subscore}</span></td>
                <td><Rich text={m.explanation.replace(/baseline/g, "usual") + (m.evidence.length ? " " + m.evidence.join(" ") : "")} seek={seek} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="more">
        <summary>How this score works</summary>
        <p>{p.method} Working together in this video: {p.context.collaboration_s_per_min} s per minute (shown for context, not scored).</p>
      </details>

      <Drift clip={clip} />
    </div>
  );
}
