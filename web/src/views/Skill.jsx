import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Dial, Radar } from "../ui.jsx";
import { Rich } from "./Copilot.jsx";

const PATTERN_CLASS = { "Expert-like": "ok", Developing: "warn", "Beginner-like": "bad" };
const SHOW = { "Expert-like": "Practised", Developing: "Developing", "Beginner-like": "New to it" };
const PATTERN_COLOR = { "Expert-like": "var(--green)", Developing: "var(--amber)", "Beginner-like": "var(--red)" };
const TONE_CLASS = { expert: "ok", typical: "warn", beginner: "bad" };

// Every recording: x = expertise axis (what the clusters are cut on), y = working style.
function ClusterMap({ points, clip, setClip, size = 300 }) {
  const pad = 22;
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (x) => pad + ((x - x0) / (x1 - x0 || 1)) * (size - 2 * pad);
  const sy = (y) => size - pad - ((y - y0) / (y1 - y0 || 1)) * (size - 2 * pad);
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="skmap" role="img" aria-label="Recordings clustered by motion pattern">
      <line x1={pad} y1={size - pad} x2={size - pad} y2={size - pad} stroke="var(--line)" />
      <text x={size - pad} y={size - 6} textAnchor="end" className="svgmuted">more practised →</text>
      <text x={8} y={pad} className="svgmuted" transform={`rotate(-90 8 ${pad})`} textAnchor="end">style</text>
      {points.map((p) => (
        <g key={p.clip_id} className="skpt" onClick={() => setClip(p.clip_id)}>
          <title>{`${p.clip_id}: ${SHOW[p.pattern] || p.pattern}`}</title>
          <circle cx={sx(p.x)} cy={sy(p.y)} r={p.clip_id === clip ? 8 : 5} fill={PATTERN_COLOR[p.pattern]}
                  fillOpacity={p.clip_id === clip ? 1 : 0.7}
                  stroke={p.clip_id === clip ? "var(--fg)" : "none"} strokeWidth="2" />
        </g>
      ))}
    </svg>
  );
}

export default function Skill({ clip, seek, setClip }) {
  const [p, setP] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setP(null); setErr(null);
    api.skill(clip).then(setP).catch((e) => setErr(e.message));
  }, [clip]);
  if (err) return <div className="error">{err}</div>;
  if (!p) return <div className="boot-inline">Looking at how the hands move…</div>;
  return (
    <div className="prof">
      <div className="cmp-h">
        <div>
          <h2>Motion skill profile · {clip}</h2>
          <p className="muted">
            Learned from {p.movements} hand movements, compared with the other {p.station_recordings - 1} video{p.station_recordings === 2 ? "" : "s"} at this station.
            {" "}It is about the movement, never the person, and no one is identified.
          </p>
        </div>
      </div>

      <div className="prof-top">
        <div className="panel glass prof-score">
          <Dial value={p.expertise_index} label="hand skill" />
          <span className={"pill " + PATTERN_CLASS[p.pattern]}>{SHOW[p.pattern] || p.pattern}</span>
          <p className="muted small">How sure: {Math.round(100 * p.confidence)}%. 50 means usual for this station.</p>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Hand movement profile</h3><span className="muted">outside the ring = more practised</span></div>
          <Radar data={p.fingerprint} />
        </div>
        <div className="panel glass">
          <div className="panel-h">
            <h3>All videos at this station</h3>
            <span className="sklegend">
              {Object.keys(PATTERN_COLOR).map((k) => <span key={k}><i style={{ background: PATTERN_COLOR[k] }} />{SHOW[k] || k}</span>)}
            </span>
          </div>
          <ClusterMap points={p.clusters} clip={clip} setClip={setClip} />
        </div>
      </div>

      <div className="panel glass sksum">The hands in this video move like someone who is <b>{(SHOW[p.pattern] || p.pattern).toLowerCase()}</b>, compared with other videos at this station.</div>

      <h3 className="sec">What the hands did</h3>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>What</th><th>This video</th><th>Usual</th><th>Looks</th><th>See it</th></tr></thead>
          <tbody>
            {p.features.map((f) => (
              <tr key={f.feature}>
                <td>{f.label}</td>
                <td className="num">{f.value}{f.unit && " " + f.unit}</td>
                <td className="num muted">{f.station_median}{f.unit && " " + f.unit}</td>
                <td><span className={"pill " + TONE_CLASS[f.tone]}>{f.tone}</span></td>
                <td>{f.evidence.length ? <Rich text={f.evidence.join(" ")} seek={seek} /> : <span className="muted">–</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="sec">Videos with similar hand movement</h3>
      <div className="sksim">
        {p.similar.map((s) => (
          <button key={s.clip_id} className="chip" onClick={() => setClip(s.clip_id)}>
            {s.clip_id} <span className={"pill " + PATTERN_CLASS[s.pattern]}>{SHOW[s.pattern] || s.pattern}</span>
          </button>
        ))}
      </div>
      <details className="more">
        <summary>How this works</summary>
        <p>{p.summary}</p>
        <p>{p.method}</p>
      </details>
    </div>
  );
}
