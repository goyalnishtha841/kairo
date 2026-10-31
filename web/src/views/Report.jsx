import React from "react";
import { fmt, LABEL } from "../api.js";

export default function Report({ report, clips }) {
  const r = report;
  const f = r.friction;
  const metrics = clips.map((c) => c.metrics).filter((m) => m && m.clip_id);
  const avg = (k) => metrics.length ? metrics.reduce((a, m) => a + (m[k] || 0), 0) / metrics.length : null;
  const date = new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  return (
    <div className="report">
      <div className="rep-h">
        <div>
          <h2>Shift Summary</h2>
          <p className="muted">{date} · {r.clips.length} clips · {r.observed_min} min observed · extrapolated to {r.shift_hours}h shift</p>
        </div>
        <button className="ghost" onClick={() => window.print()}>Export PDF</button>
      </div>

      <div className="tiles">
        <div className="tile"><span>Work steps</span><b>{r.steps}</b><small>avg {r.avg_step_s}s</small></div>
        <div className="tile"><span>Hands-on work</span><b>{r.breakdown_pct.work ?? 0}%</b></div>
        <div className="tile"><span>Search time</span><b>{r.breakdown_pct.search ?? 0}%</b><small>{f.search.count} events</small></div>
        <div className="tile"><span>Idle / waiting</span><b>{r.breakdown_pct.idle ?? 0}%</b><small>{f.idle.count} events</small></div>
        <div className="tile"><span>Hesitations</span><b>{f.hesitation.count}</b><small>{f.hesitation.seconds}s</small></div>
        <div className="tile red"><span>Est. lost time</span><b>{r.lost_min_per_shift}</b><small>min / shift</small></div>
      </div>

      <h3 className="sec">Top recommendations</h3>
      <ol className="replist">
        {r.recommendations.slice(0, 4).map((x, i) => (
          <li key={i}><b>{x.title}</b>: saves ~{x.saving_min_per_shift} min/shift. <span className="muted">{x.support}.</span></li>
        ))}
      </ol>

      {r.longest_step && (
        <>
          <h3 className="sec">Bottleneck</h3>
          <p>Longest step: <b>{r.longest_step.label}</b> in {r.longest_step.clip_id} at {fmt(r.longest_step.t_start)}, {r.longest_step.duration_s.toFixed(1)}s (average {r.avg_step_s}s).</p>
        </>
      )}

      <h3 className="sec">Friction detail</h3>
      <table className="tbl">
        <thead><tr><th>Type</th><th>Events</th><th>Seconds observed</th></tr></thead>
        <tbody>
          {Object.entries(f).map(([k, v]) => (
            <tr key={k}><td>{LABEL[k]}</td><td>{v.count}</td><td>{v.seconds}</td></tr>
          ))}
        </tbody>
      </table>

      {metrics.length > 0 && (
        <>
          <h3 className="sec">Hand-tracking quality</h3>
          <table className="tbl">
            <thead><tr><th>Clip</th><th>Frames w/ hands</th><th>Mean confidence</th><th>Jitter raw → smoothed (px)</th><th>Other people's hands rejected</th><th>Speed (FPS, CPU)</th></tr></thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.clip_id}>
                  <td>{m.clip_id}</td>
                  <td>{Math.round(m.detection_rate_any_hand * 100)}%</td>
                  <td>{m.mean_confidence}</td>
                  <td>{m.jitter_px_raw} → {m.jitter_px_smoothed} (−{m.jitter_reduction_pct}%)</td>
                  <td>{m.other_person_hands_rejected ?? "–"}</td>
                  <td>{m.processing_fps}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">Average smoothing gain: −{avg("jitter_reduction_pct")?.toFixed(1)}% jitter. Frames without hands are mostly the worker looking away from the work, which the timeline counts as search/idle.</p>
        </>
      )}
      <p className="muted small">Kairo evaluates the process and the workstation, not individual workers. {r.assumptions.note}</p>
    </div>
  );
}
