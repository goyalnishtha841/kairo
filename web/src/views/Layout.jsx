import React from "react";
import { COLOR, fmt, LABEL } from "../api.js";

// Top-down sketch of the work area: worker at the bottom, three zones in an arc.
// Red heat = where the head turned while searching; green = where hands actually worked.
function StationMap({ dirs = {}, work = {}, suggested }) {
  const maxS = Math.max(1, ...Object.values(dirs));
  const maxW = Math.max(1, ...Object.values(work));
  const zones = [
    { k: "left", x: 70, y: 150 },
    { k: "center", x: 200, y: 70 },
    { k: "right", x: 330, y: 150 },
  ];
  return (
    <svg viewBox="0 0 400 300" className="map">
      <path d="M40 270 A170 170 0 0 1 360 270" fill="none" stroke="var(--line)" strokeDasharray="4 6" />
      <text x="200" y="292" textAnchor="middle" className="svgmuted">worker</text>
      <circle cx="200" cy="262" r="14" fill="var(--panel2)" stroke="var(--fg2)" />
      {zones.map((z) => {
        const s = (dirs[z.k] || 0) / maxS, w = (work[z.k] || 0) / maxW;
        return (
          <g key={z.k}>
            <circle cx={z.x} cy={z.y} r={18 + 34 * s} fill="var(--red)" opacity={0.15 + 0.5 * s} />
            <circle cx={z.x} cy={z.y} r={10 + 18 * w} fill="var(--green)" opacity={0.35 + 0.5 * w} />
            <text x={z.x} y={z.y + 62} textAnchor="middle" className="svglabel">{z.k}</text>
            <text x={z.x} y={z.y + 78} textAnchor="middle" className="svgmuted">
              {dirs[z.k] || 0} searches · {Math.round(work[z.k] || 0)}s work
            </text>
          </g>
        );
      })}
      {suggested && (
        <g>
          <rect x="160" y="168" width="80" height="34" rx="6" fill="none" stroke="var(--accent)" strokeWidth="2" strokeDasharray="5 4" />
          <text x="200" y="190" textAnchor="middle" className="svgaccent">tool cart</text>
        </g>
      )}
    </svg>
  );
}

export default function Layout({ report, seek }) {
  const recs = report.recommendations;
  const b = report.breakdown_pct;
  return (
    <div className="layout">
      {report.headline && (
        <div className="hero">
          <div className="hero-n">{recs[0]?.saving_min_per_shift ?? 0}<span>min / shift</span></div>
          <p>{report.headline}</p>
        </div>
      )}

      <div className="grid2">
        <div className="panel">
          <div className="panel-h"><h3>Where time goes</h3><span className="muted">{report.observed_min} min observed</span></div>
          <div className="stack">
            {Object.entries(b).sort((x, y) => y[1] - x[1]).map(([k, v]) => (
              <div key={k} style={{ width: `${v}%`, background: COLOR[k] }} title={`${LABEL[k]} ${v}%`} />
            ))}
          </div>
          <div className="legend">
            {Object.entries(b).sort((x, y) => y[1] - x[1]).map(([k, v]) => (
              <span key={k}><i style={{ background: COLOR[k] }} />{LABEL[k]} {v}%</span>
            ))}
          </div>
          <div className="bign">
            <div><b>{report.lost_min_per_shift}</b><span>min/shift lost to friction</span></div>
            <div><b className="acc">{report.recoverable_min_per_shift}</b><span>min/shift recoverable</span></div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><h3>Station map</h3><span className="muted">current vs suggested</span></div>
          <StationMap dirs={report.search_directions} work={report.work_zones} suggested={recs.some((r) => r.kind === "layout")} />
          <div className="legend">
            <span><i style={{ background: "var(--red)" }} />Search direction</span>
            <span><i style={{ background: "var(--green)" }} />Hands-on work</span>
            <span><i className="dash" />Suggested tool position</span>
          </div>
        </div>
      </div>

      <h3 className="sec">Recommendations</h3>
      <div className="recs">
        {recs.map((r, i) => (
          <div key={i} className="rec">
            <div className="rec-h">
              <span className={"kind " + r.kind}>{r.kind}</span>
              <b>{r.title}</b>
              <span className="save">−{r.saving_min_per_shift} min/shift <small>({r.cycle_time_reduction_pct}% time)</small></span>
            </div>
            <p>{r.detail}</p>
            <div className="evid">
              <span className="muted">Evidence · {r.support}:</span>
              {r.evidence.map((e) => (
                <a key={e.id + e.clip_id} className="cite" onClick={() => seek(e.clip_id, e.t)} title={e.note}>
                  ▶ {e.clip_id.slice(-3)} {fmt(e.t)} ({e.dur}s)
                </a>
              ))}
            </div>
          </div>
        ))}
        {!recs.length && <div className="muted">No significant friction detected.</div>}
      </div>
      <p className="muted small">
        Savings assume a fix removes {Object.entries(report.assumptions.recoverable_fraction).map(([k, v]) => `${Math.round(v * 100)}% of ${LABEL[k].toLowerCase()}`).join(", ")}.
        {" "}{report.assumptions.note}
      </p>
    </div>
  );
}
