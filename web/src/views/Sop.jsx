import React, { useState } from "react";
import { api, fmt } from "../api.js";

function Compliance({ clip, seek }) {
  const [text, setText] = useState("");
  const [mandatory, setMandatory] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const check = () => {
    const steps = text.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!steps.length) return;
    const mand = mandatory.split(",").map((s) => s.trim()).filter(Boolean);
    setBusy(true);
    setErr(null);
    api.sopCompliance(clip, steps, mand).then(setResult).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };

  return (
    <div className="compliance">
      <h3 className="sec">SOP compliance check</h3>
      <p className="muted small">
        Paste the written SOP (one step per line, in order) and check this recording against it:
        missing steps, out-of-order steps, extra steps, and any skipped mandatory step (e.g. an inspection).
      </p>
      <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
        <textarea rows={6} style={{ flex: 1, minWidth: 220 }} placeholder={"Open panel\nDisconnect power\nRemove screw\nInspect\nClose panel"}
                  value={text} onChange={(e) => setText(e.target.value)} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <label className="muted small" style={{ display: "block", marginBottom: 4 }}>Mandatory steps (comma-separated, must never be skipped)</label>
          <input style={{ width: "100%" }} placeholder="Inspect" value={mandatory} onChange={(e) => setMandatory(e.target.value)} />
          <button className="ghost" style={{ marginTop: 10 }} disabled={busy || !text.trim()} onClick={check}>
            {busy ? "Checking…" : "Check compliance"}
          </button>
        </div>
      </div>
      {err && <p className="warn">{err}</p>}
      {result && (
        <div className="compliance-result">
          <p className={result.compliant ? "" : "warn"}>
            <b>{result.compliant ? "✓ " : "⚠ "}{result.headline}</b> ({result.adherence_pct}% adherence)
          </p>
          <table className="tbl">
            <thead><tr><th>Expected step</th><th>Status</th><th>Matched to</th><th>When</th></tr></thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  <td>{row.expected}</td>
                  <td className={row.status === "missing" ? "warn" : row.status === "out_of_order" ? "warn" : ""}>
                    {row.status === "done" ? "✓ done" : row.status === "out_of_order" ? "out of order" : "missing"}
                  </td>
                  <td className="muted">{row.matched_label || "–"}</td>
                  <td>{row.cite ? <a className="cite" onClick={() => seek(clip, row.t_start)}>▶ {fmt(row.t_start)}</a> : "–"}</td>
                </tr>
              ))}
              {result.extra_steps.map((e) => (
                <tr key={`extra-${e.step_id}`}>
                  <td className="muted">(extra, not in SOP)</td>
                  <td>extra</td>
                  <td>{e.label}</td>
                  <td><a className="cite" onClick={() => seek(clip, e.t_start)}>▶ {fmt(e.t_start)}</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

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
      <Compliance clip={clip} seek={seek} />
    </div>
  );
}
