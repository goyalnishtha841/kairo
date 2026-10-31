import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Dial } from "../ui.jsx";
import { Rich } from "./Copilot.jsx";

const MARK = { ok: "✓", warn: "⚠", fail: "✗", na: "–" };
const CLS = { ok: "ok", warn: "warn", fail: "bad", na: "" };
const GRADE = { Good: "ok", Fair: "warn", Poor: "bad" };
const NAME = { sequence: "Sequence", tools: "Tools", time: "Time vs baseline", movement: "Movement", flow: "Flow" };
const station = (id) => id.replace(/-[^-]+$/, "");
const stepCls = (s) => (s >= 85 ? "ok" : s >= 60 ? "warn" : "bad");

export default function Quality({ clip, clips, seek, setClip }) {
  const [ref, setRef] = useState("");
  const [q, setQ] = useState(null);
  const [err, setErr] = useState(null);
  const peers = clips.filter((c) => station(c) === station(clip) && c !== clip);
  useEffect(() => { setRef(""); }, [clip]);
  useEffect(() => {
    setQ(null); setErr(null);
    api.quality(clip, ref).then(setQ).catch((e) => setErr(e.message));
  }, [clip, ref]);
  if (err) return <div className="error">{err}</div>;
  if (!q) return <div className="boot-inline">Scoring task quality…</div>;
  return (
    <div className="prof">
      <div className="cmp-h">
        <div>
          <h2>Quality score · {clip}</h2>
          <p className="muted">
            Compared with {q.baseline_recordings} other recording{q.baseline_recordings === 1 ? "" : "s"} of station {q.station}
            {" "}(reliability: <b>{q.reliability}</b>). {q.note}
          </p>
        </div>
        <label className="qref">
          <span className="muted small">Reference SOP (same task)</span>
          <select value={ref} onChange={(e) => setRef(e.target.value)}>
            <option value="">None: skip sequence and tools</option>
            {peers.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>

      <div className="prof-top qtop">
        <div className="panel glass prof-score">
          <Dial value={q.score} label="quality score" />
          {q.grade && <span className={"pill " + GRADE[q.grade]}>{q.grade}</span>}
          <p className="muted small">Based on {q.measured_weight} of 100 points that could be measured here.</p>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Why this score</h3><span className="muted">points / weight</span></div>
          <ul className="qchecks">
            {q.checks.map((c) => (
              <li key={c.check} className={"q-" + c.status}>
                <span className={"qmark " + CLS[c.status]}>{MARK[c.status]}</span>
                <div>
                  <b>{NAME[c.check]}</b> <span className="muted small">{c.points == null ? "n/a" : `${c.points} / ${c.weight}`}</span>
                  <div><Rich text={c.reason} seek={seek} /></div>
                  {c.details.map((d, i) => <div key={i} className="muted small"><Rich text={d} seek={seek} /></div>)}
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Station recordings</h3><span className="muted">{q.station}</span></div>
          <div className="curve">
            {q.station_scores.map((c) => (
              <button key={c.clip_id} className={"cbar" + (c.clip_id === clip ? " on" : "")} title={`${c.clip_id}: ${c.score}`}
                      onClick={() => setClip(c.clip_id)}>
                <i style={{ height: `${c.score ?? 0}%` }} />
                <span>{c.clip_id.slice(-3)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      <h3 className="sec">Quality per step</h3>
      <div className="qsteps">
        {q.steps.map((s) => (
          <div key={s.step_id} className="panel glass qstep">
            <div className="qstep-h">
              <a className="cite" onClick={() => seek(s.t_start)}>Step {s.step_id}</a>
              <b>{s.label}</b>{s.tool && <span className="muted"> · {s.tool}</span>}
              <span className={"pill " + stepCls(s.score)}>{s.score}/100</span>
            </div>
            <ul>
              {s.reasons.map((r, i) => (
                <li key={i}><span className={"qmark " + CLS[r.status]}>{MARK[r.status]}</span> <Rich text={r.text} seek={seek} /></li>
              ))}
              {!s.timed && <li className="muted small">Cut off by the recording's start or end, so not timed.</li>}
            </ul>
          </div>
        ))}
      </div>
      <p className="muted small">{q.method} Pick a reference recording of the same task: consecutive chunks of one long job are different tasks and will show a low sequence score.</p>
    </div>
  );
}
