import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Dial, Radar } from "../ui.jsx";
import { Rich } from "./Copilot.jsx";

const PATTERN_CLASS = { "Expert-like": "ok", Developing: "warn", "Beginner-like": "bad" };
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
      <text x={size - pad} y={size - 6} textAnchor="end" className="svgmuted">more expert-like →</text>
      <text x={8} y={pad} className="svgmuted" transform={`rotate(-90 8 ${pad})`} textAnchor="end">working style</text>
      {points.map((p) => (
        <g key={p.clip_id} className="skpt" onClick={() => setClip(p.clip_id)}>
          <title>{`${p.clip_id}: ${p.pattern}`}</title>
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
  if (!p) return <div className="boot-inline">Profiling hand motion…</div>;
  return (
    <div className="prof">
      <div className="cmp-h">
        <div>
          <h2>Motion skill profile · {clip}</h2>
          <p className="muted">
            Learned without labels from how the hands move, compared with the {p.station_recordings} recording
            {p.station_recordings === 1 ? "" : "s"} of station {p.station} (reliability: <b>{p.reliability}</b>,
            {" "}{p.movements} hand movements). {p.note}
          </p>
        </div>
      </div>

      <div className="prof-top">
        <div className="panel glass prof-score">
          <Dial value={p.expertise_index} label="expertise index" />
          <span className={"pill " + PATTERN_CLASS[p.pattern]}>{p.pattern}</span>
          <p className="muted small">Cluster confidence {Math.round(100 * p.confidence)}%. 50 = the station's typical motion.</p>
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Motion fingerprint</h3><span className="muted">outer = more expert-like · ring = station</span></div>
          <Radar data={p.fingerprint} />
        </div>
        <div className="panel glass">
          <div className="panel-h">
            <h3>Clusters</h3>
            <span className="sklegend">
              {Object.keys(PATTERN_COLOR).map((k) => <span key={k}><i style={{ background: PATTERN_COLOR[k] }} />{k}</span>)}
            </span>
          </div>
          <ClusterMap points={p.clusters} clip={clip} setClip={setClip} />
        </div>
      </div>

      <div className="panel glass sksum"><Rich text={p.summary} seek={seek} /></div>

      <h3 className="sec">What the hands show</h3>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Feature</th><th>This recording</th><th>Station median</th><th>Reads as</th><th>Evidence</th></tr></thead>
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

      <h3 className="sec">Most similar motion</h3>
      <div className="sksim">
        {p.similar.map((s) => (
          <button key={s.clip_id} className="chip" onClick={() => setClip(s.clip_id)}>
            {s.clip_id} <span className={"pill " + PATTERN_CLASS[s.pattern]}>{s.pattern}</span>
          </button>
        ))}
      </div>
      <p className="muted small">{p.method}</p>
    </div>
  );
}
