import React, { useEffect, useState } from "react";
import { api, COLOR, fmt, LABEL } from "../api.js";
import { CountUp } from "../ui.jsx";

// Top-down sketch of the work area: worker at the bottom, three zones in an arc.
// Red = where the head turned while searching; green = where hands actually worked.
// When a layout fix is recommended, draws an arrow from the most-searched zone to the
// most-worked zone -- "move the tool here" -- derived from the same measured zone data,
// never a guessed tool position (there is no tool detector to place one precisely).
const ZONE_POS = { left: { x: 70, y: 150 }, center: { x: 200, y: 70 }, right: { x: 330, y: 150 } };

function StationMap({ dirs = {}, work = {}, layoutRec }) {
  const maxS = Math.max(1, ...Object.values(dirs));
  const maxW = Math.max(1, ...Object.values(work));
  const zones = Object.keys(ZONE_POS).map((k) => ({ k, ...ZONE_POS[k] }));
  const topSearch = Object.entries(dirs).sort((a, b) => b[1] - a[1])[0]?.[0];
  const topWork = Object.entries(work).sort((a, b) => b[1] - a[1])[0]?.[0];
  const showArrow = layoutRec && topSearch && topWork && topSearch !== topWork;
  const from = showArrow ? ZONE_POS[topSearch] : null;
  const to = showArrow ? ZONE_POS[topWork] : null;
  const mid = showArrow ? { x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 40 } : null;
  return (
    <svg viewBox="0 0 400 320" className="map" role="img" aria-label="Station map of search directions and work zones">
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
      {showArrow && (
        <g>
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
              <path d="M0,0 L8,4 L0,8 Z" fill="var(--accent)" />
            </marker>
          </defs>
          <path d={`M${from.x},${from.y} Q${mid.x},${mid.y} ${to.x},${to.y}`} fill="none" stroke="var(--accent)"
                strokeWidth="2" strokeDasharray="5 4" markerEnd="url(#arrowhead)" />
          <rect x={to.x - 46} y={to.y - 46} width="92" height="26" rx="6" fill="none" stroke="var(--accent)"
                strokeWidth="2" strokeDasharray="3 3" />
          <text x={to.x} y={to.y - 29} textAnchor="middle" className="svgaccent">suggested spot</text>
        </g>
      )}
      {showArrow && (
        <text x="200" y="312" textAnchor="middle" className="svgmuted">
          {layoutRec.title}: moving the {topSearch}-zone tool to {topWork} saves ~{layoutRec.saving_min_per_shift} min/shift
        </text>
      )}
    </svg>
  );
}

function Bars({ states, total }) {
  return (
    <div className="simbar">
      {states.map((s, i) => (
        <div key={i} style={{ left: `${(100 * s.t_start) / total}%`, width: `${(100 * (s.t_end - s.t_start)) / total}%`, background: COLOR[s.state] }} />
      ))}
    </div>
  );
}

function Simulation({ rec }) {
  const [sim, setSim] = useState(null);
  const [err, setErr] = useState(null);
  const ev = rec.evidence[0];
  useEffect(() => {
    if (!ev) return;
    api.simulate(ev.clip_id, rec.friction_type).then(setSim).catch((e) => setErr(e.message));
  }, [ev?.clip_id, rec.friction_type]);
  if (err) return <div className="error">{err}</div>;
  if (!sim) return <div className="muted small pad">Simulating…</div>;
  return (
    <div className="sim">
      <div className="simrow"><span className="muted">Today</span><Bars states={sim.before} total={sim.duration_before} /><span className="t">{fmt(sim.duration_before)}</span></div>
      <div className="simrow"><span className="acc">With fix</span><Bars states={sim.after} total={sim.duration_before} /><span className="t acc">{fmt(sim.duration_after)}</span></div>
      <p className="muted small">
        {sim.clip_id}: removing {Math.round(sim.recoverable_share * 100)}% of each {LABEL[rec.friction_type].toLowerCase()} event
        saves <b>{sim.saved_s}s</b> in this {fmt(sim.duration_before)} recording.
      </p>
    </div>
  );
}

function Rec({ r, rank, seek }) {
  const [open, setOpen] = useState(rank === 0);
  const c = Math.round(r.confidence * 100);
  return (
    <div className={"rec glass" + (rank === 0 ? " rec-best" : "")}>
      <div className="rec-h">
        <span className={"kind " + r.kind}>{r.kind}</span>
        <b>{r.title}</b>
        <span className="save">€{r.roi_eur_per_year.toLocaleString()}<small>/yr</small></span>
      </div>
      <div className="rec-grid">
        <div>
          <p className="obs">{r.observation}</p>
          <p className="act">→ {r.action}</p>
        </div>
        <div className="rec-stats">
          <div><b>{r.saving_min_per_shift}</b><span>min / shift</span></div>
          <div><b>{r.evidence_stats.events}</b><span>events</span></div>
          <div><b>{r.evidence_stats.clips}/{r.evidence_stats.of_clips}</b><span>clips</span></div>
          <div className="conf" title={r.confidence_method}>
            <span>Confidence {c}%</span>
            <div className="confbar"><i style={{ width: `${c}%` }} /></div>
          </div>
        </div>
      </div>
      <div className="evid">
        <span className="muted">Evidence:</span>
        {r.evidence.map((e) => (
          <a key={e.id + e.clip_id} className="cite" onClick={() => seek(e.clip_id, e.t)} title={e.note}>
            ▶ {e.clip_id.slice(-6)} {fmt(e.t)} ({e.dur}s)
          </a>
        ))}
        <button className="ghost sm right" onClick={() => setOpen(!open)}>{open ? "Hide simulation" : "Simulate fix"}</button>
      </div>
      {open && <Simulation rec={r} />}
    </div>
  );
}

function Safety({ clips, seek }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    Promise.all(clips.map((c) => api.safety(c))).then(setRows).catch(() => setRows([]));
  }, [clips.join(",")]);
  if (!rows) return null;
  const configured = rows.filter((r) => r.configured);
  const forecasts = configured.flatMap((r) => r.forecasts.map((f) => ({ ...f, clip_id: r.clip_id })));
  return (
    <div className="panel glass">
      <div className="panel-h"><h3>Safety risk</h3><span className="muted">predicted, not just detected</span></div>
      {!configured.length ? (
        <p className="muted small">No unsafe zone is configured for any station in this shift, so safety risk
          cannot be measured yet -- that is not the same as "safe". Configure events/config.py's UNSAFE_ZONES
          for a station to turn this on.</p>
      ) : forecasts.length ? (
        <>
          <ul className="replist">
            {forecasts.slice(0, 5).map((f, i) => (
              <li key={i}>
                <b>{Math.round(f.probability_next_window * 100)}% chance</b> of another unsafe reach in the next
                {" "}{f.window_s}s <span className="muted">({f.recent_count} in the last {f.window_s}s)</span>{" "}
                <a className="cite" onClick={() => seek(f.clip_id, f.t)}>▶ {fmt(f.t)}</a>
              </li>
            ))}
          </ul>
          <p className="muted small">Poisson-rate extrapolation from recent unsafe-reach frequency -- a heuristic, not a trained model.</p>
        </>
      ) : (
        <p className="muted small">Unsafe zones configured ({configured.map((r) => r.unsafe_zones.join("/")).join(", ")}), no repeated unsafe reaches detected.</p>
      )}
    </div>
  );
}

export default function Impact({ report, seek }) {
  const recs = report.recommendations;
  const b = report.breakdown_pct;
  const a = report.assumptions;
  const layoutRec = recs.find((r) => r.kind === "layout");
  return (
    <div className="impact">
      <div className="hero glass">
        <div className="hero-n"><span className="eur">€<CountUp to={report.roi_eur_per_year_total} /></span><span>per station per year</span></div>
        <div className="hero-side">
          <div><b><CountUp to={report.recoverable_min_per_shift} decimals={1} /></b><span>min / shift recoverable</span></div>
          <div><b>{recs.length}</b><span>evidence-backed fixes</span></div>
          <div><b>{report.observed_min}</b><span>min of footage analysed</span></div>
        </div>
        <p className="hero-p">{report.headline}</p>
      </div>

      <h3 className="sec">Recommendations, ranked by ROI</h3>
      <div className="recs">
        {recs.map((r, i) => <Rec key={r.friction_type} r={r} rank={i} seek={seek} />)}
        {!recs.length && <div className="muted">No significant friction detected.</div>}
      </div>

      <div className="grid2" style={{ marginTop: 16 }}>
        <div className="panel glass">
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
        </div>
        <div className="panel glass">
          <div className="panel-h"><h3>Station map</h3><span className="muted">search direction vs work</span></div>
          <StationMap dirs={report.search_directions} work={report.work_zones} layoutRec={layoutRec} />
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <Safety clips={report.clips} seek={seek} />
      </div>
      <p className="muted small">
        ROI = minutes per shift × €{a.labor_eur_per_hour}/h × {a.shifts_per_day} shifts × {a.workdays_per_year} days.
        A fix removes {Object.entries(a.recoverable_fraction).map(([k, v]) => `${Math.round(v * 100)}% of ${LABEL[k].toLowerCase()}`).join(", ")}.
        Confidence = 0.5 × evidence volume + 0.3 × spread across clips + 0.2 × consistency. {a.note}
      </p>
    </div>
  );
}
