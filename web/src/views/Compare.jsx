import React, { useEffect, useState } from "react";
import { api, fmt } from "../api.js";
import { Rich } from "./Copilot.jsx";

const STATUS = {
  match: ["Matches", "ok"],
  faster: ["Faster", "ok"],
  slower: ["Slower", "warn"],
  missing: ["Missing", "bad"],
  extra: ["Extra", "warn"],
  out_of_order: ["Out of order", "bad"],
};

export default function Compare({ clips, seek }) {
  const ids = clips.map((c) => c.clip_id);
  const [ref, setRef] = useState(ids[0]);
  const [tgt, setTgt] = useState(ids[1] || ids[0]);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!ref || !tgt) return;
    setErr(null);
    api.compare(ref, tgt).then(setRes).catch((e) => setErr(e.message));
  }, [ref, tgt]);

  const Step = ({ s, clip }) => s ? (
    <a className="stepref" onClick={() => seek(clip, s.t_start)}>
      <b>{s.label}</b>
      <small>{fmt(s.t_start)} · {s.duration_s.toFixed(0)}s{s.tool ? ` · ${s.tool}` : ""}</small>
    </a>
  ) : <span className="muted">-</span>;

  return (
    <div className="compare">
      <div className="cmp-h">
        <div>
          <h2>SOP Comparator</h2>
          <p className="muted">Pick a good example video, then a video to check against it.</p>
        </div>
        <div className="pickers">
          <label>Good example<select value={ref} onChange={(e) => setRef(e.target.value)}>{ids.map((i) => <option key={i}>{i}</option>)}</select></label>
          <span className="vs">vs</span>
          <label>Video to check<select value={tgt} onChange={(e) => setTgt(e.target.value)}>{ids.map((i) => <option key={i}>{i}</option>)}</select></label>
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      {res && (
        <>
          <div className="tiles">
            <div className="tile"><span>Steps followed</span><b>{res.adherence_pct}%</b><small>of the example's steps</small></div>
            <div className="tile"><span>Missing</span><b>{res.counts.missing}</b></div>
            <div className="tile"><span>Out of order</span><b>{res.counts.out_of_order}</b></div>
            <div className="tile"><span>Extra steps</span><b>{res.counts.extra}</b></div>
            <div className="tile"><span>Slower steps</span><b>{res.counts.slower}</b></div>
            <div className={"tile " + (res.hands_on_s.delta > 0 ? "red" : "")}><span>Hands-on time</span><b>{res.hands_on_s.delta > 0 ? "+" : ""}{res.hands_on_s.delta}s</b><small>{res.hands_on_s.target}s vs {res.hands_on_s.reference}s</small></div>
          </div>

          <div className="grid2 cmp-body">
            <div className="panel">
              <div className="panel-h"><h3>Step by step</h3><span className="muted">example ↔ checked</span></div>
              <table className="tbl flat">
                <thead><tr><th>Example</th><th>Checked video</th><th>Result</th></tr></thead>
                <tbody>
                  {res.rows.map((r, i) => (
                    <tr key={i}>
                      <td><Step s={r.ref} clip={res.reference} /></td>
                      <td><Step s={r.target} clip={res.target} /></td>
                      <td><span className={"pill " + STATUS[r.status][1]}>{STATUS[r.status][0]}</span>
                        {r.delta_pct != null && r.status !== "match" && <small className="muted"> {r.delta_pct > 0 ? "+" : ""}{r.delta_pct}%</small>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="panel">
              <div className="panel-h"><h3>What's different</h3><span className="muted">{res.findings.length}</span></div>
              <ul className="findings">
                {res.findings.slice(0, 14).map((f, i) => <li key={i}><Rich text={f} seek={seek} /></li>)}
                {!res.findings.length && <li className="muted">The checked video follows the example.</li>}
              </ul>
              <p className="muted small pad">Steps are matched by their name and order. Compare two videos of the same job, like two runs of one task.</p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
