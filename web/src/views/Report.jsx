import React, { useEffect, useState } from "react";
import { api, fmt, LABEL } from "../api.js";

const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);

function Accuracy({ acc }) {
  const rows = [
    ["Precision (whole video)", "drawn hands that really are the wearer's hand", "precision_weighted"],
    ["Recall (whole video)", "wearer's visible hands that were found", "recall_weighted"],
    ["Precision (hard sample)", "on the 50/50 found / not-found sample", "precision"],
    ["Recall (hard sample)", "the sample over-weights frames where hands were missed", "recall"],
    ["F1", "balance of the two", "f1"],
    ["Left / Right", "found hands with the correct side", "left_right_accuracy"],
    ["Frame presence", "frames where 'hands in view' is right", "frame_presence_accuracy"],
  ];
  return (
    <>
      <h3 className="sec">Hand-tracking accuracy (human-labelled)</h3>
      <table className="tbl">
        <thead><tr><th>Measure</th><th>What it means</th>{acc.baseline && <th>Before tuning</th>}<th>After tuning (tuning clips)</th>{acc.heldout && <th>Held-out clips</th>}</tr></thead>
        <tbody>
          {rows.map(([name, desc, k]) => (
            <tr key={k}>
              <td>{name}</td><td className="muted">{desc}</td>
              {acc.baseline && <td>{pct(acc.baseline[k])}</td>}
              <td>{pct(acc[k])}</td>
              {acc.heldout && <td><b>{pct(acc.heldout[k])}</b></td>}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Tuning set: {acc.frames_labelled} hand-labelled frames from {acc.clips} clips, used to choose the detection threshold and the left/right rule.
        {acc.heldout && <> Held-out set: {acc.heldout.frames_labelled} frames from {acc.heldout.clips} clips that were never used for tuning; this is the honest number.</>}
        {" "}Frames are half "tracker found hands", half "found none", so misses count. Reproduce with <code>python eval/accuracy.py score</code> (add <code>--set heldout</code>).
      </p>
    </>
  );
}

function Verification({ v }) {
  const t = v.total;
  const rows = [
    ["Precision", "drawn hands that really are the wearer's hand", "precision"],
    ["Recall", "wearer's visible hands that were found", "recall"],
    ["Frame presence", "frames where 'hands in view' is right", "frame_presence"],
  ];
  return (
    <>
      <h3 className="sec">Temporal verification (false-positive and flicker control)</h3>
      <p>
        A hand is accepted from its track over time, not from one frame. Dropouts up to {v.params.max_gap_s}s are bridged
        when the motion is consistent (the hand reappears where it was heading, at the same size); one-frame detections
        below {Math.round(v.params.solo_conf * 100)}% confidence are rejected. Hand flicker: <b>{t.flicker_before} → {t.flicker_after}</b> on/off
        switches per minute (<b>−{t.flicker_reduction_pct}%</b>), {t.bridged.toLocaleString()} frames bridged, {t.rejected} blips rejected
        out of {t.detections_in.toLocaleString()} detections.
      </p>
      <table className="tbl">
        <thead><tr><th>Measure</th><th>What it means</th>
          {v.tune && <><th>Tuning clips: raw</th><th>verified</th></>}
          {v.heldout && <><th>Held-out clips: raw</th><th>verified</th></>}</tr></thead>
        <tbody>
          {rows.map(([name, desc, k]) => (
            <tr key={k}>
              <td>{name}</td><td className="muted">{desc}</td>
              {v.tune && <><td>{pct(v.tune.before[k])}</td><td>{pct(v.tune.after[k])}</td></>}
              {v.heldout && <><td>{pct(v.heldout.before[k])}</td><td><b>{pct(v.heldout.after[k])}</b></td></>}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Same human-labelled frames as above. Bridged hands count as found where a labelled hand was missed; ~29 of 32 bridged
        skeletons were checked by eye to sit on a real hand (if none did, held-out recall would stay {pct(v.heldout?.after.recall_if_bridges_wrong)}).
        {" "}{v.rejection_check} Rejecting longer or more confident short tracks was tested and removed real hands, so it is off.
        Bridged frames count as hand presence only, never as motion evidence. Reproduce with <code>python perception/verify.py --report</code>.
      </p>
    </>
  );
}

function citeToSeconds(cite) {
  const m = /@(\d{2}):(\d{2})/.exec(cite || "");
  return m ? { label: `${m[1]}:${m[2]}`, t: +m[1] * 60 + +m[2] } : null;
}

function RootCause({ findings, seek }) {
  if (!findings) return null;
  return (
    <>
      <h3 className="sec">Root cause analysis</h3>
      {findings.length ? (
        <ol className="replist">
          {findings.slice(0, 5).map((f, i) => (
            <li key={i}>
              <b>{f.step_label}</b> ({f.clip_id}): {f.root_cause} <span className="muted">Fix: {f.fix}</span>{" "}
              {f.evidence.map((c, j) => {
                const p = citeToSeconds(c);
                return p ? <a key={j} className="cite" onClick={() => seek(f.clip_id, p.t)}>▶ {p.label}</a> : null;
              })}
            </li>
          ))}
        </ol>
      ) : <p className="muted">No clustered friction pattern (e.g. repeated re-grasps, repeated searches) matches a known root cause yet.</p>}
      <p className="muted small">Deterministic pattern matching over clustered friction events, not an LLM guess -- every finding is evidence-cited.</p>
    </>
  );
}

function CollaborationScore({ clips }) {
  const [cs, setCs] = useState(null);
  useEffect(() => { api.collaborationScore(clips).then(setCs).catch(() => {}); }, [clips.join(",")]);
  if (!cs || !cs.total_collaboration_events) return null;
  return (
    <div className="tiles" style={{ marginBottom: 16 }}>
      <div className="tile"><span>Help frequency</span><b>{cs.avg_help_frequency_per_hour}</b><small>events / hour, avg</small></div>
      <div className="tile"><span>Total waiting</span><b>{cs.total_waiting_s}s</b><small>work paused for someone else</small></div>
      <div className="tile"><span>Most waiting</span><b>{cs.clip_with_most_waiting?.slice(-6) || "–"}</b><small>{cs.note}</small></div>
    </div>
  );
}

const DELAY_DIMS = [
  { k: "task", label: "Task", q: "which task causes the highest delay?" },
  { k: "friction", label: "Friction type", q: "which friction type causes the highest delay?" },
  { k: "tool", label: "Tool", q: "which tool causes the highest delay?" },
];

function KnowledgeGraph({ clips }) {
  const [dim, setDim] = useState("task");
  const [res, setRes] = useState(null);
  useEffect(() => {
    const q = DELAY_DIMS.find((d) => d.k === dim).q;
    api.knowledgeGraph(q, clips).then(setRes).catch(() => setRes(null));
  }, [dim, clips.join(",")]);
  return (
    <>
      <h3 className="sec">Knowledge graph: delay by…</h3>
      <div className="panel glass pad">
        <div className="row" style={{ marginBottom: 10 }}>
          {DELAY_DIMS.map((d) => (
            <button key={d.k} className={"ghost sm" + (dim === d.k ? " on" : "")} onClick={() => setDim(d.k)}>{d.label}</button>
          ))}
        </div>
        {!res ? <p className="muted small">Loading…</p> : (
          <>
            <p>{res.answer}</p>
            {res.rows.length > 0 && (
              <table className="tbl">
                <thead><tr><th>{DELAY_DIMS.find((d) => d.k === dim).label}</th><th>Total delay</th></tr></thead>
                <tbody>
                  {res.rows.slice(0, 8).map((row, i) => (
                    <tr key={i}><td>{row.key}</td><td>{row.total_delay_s}s</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </>
  );
}

export default function Report({ report, clips, seek }) {
  const r = report;
  const f = r.friction;
  const [acc, setAcc] = useState(null);
  const [ver, setVer] = useState(null);
  const [summary, setSummary] = useState(null);
  const [causes, setCauses] = useState(null);
  useEffect(() => { api.accuracy().then(setAcc).catch(() => {}); }, []);
  useEffect(() => { api.verification().then(setVer).catch(() => {}); }, []);
  useEffect(() => { api.shiftSummary(r.clips).then(setSummary).catch(() => {}); }, [r.clips]);
  useEffect(() => { api.rootCause(r.clips).then(setCauses).catch(() => {}); }, [r.clips]);
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
        <a className="ghost" style={{ textDecoration: "none" }}
           href={`/api/shift-report.pdf?clips=${r.clips.join(",")}&shift_hours=${r.shift_hours}`}
           download="kairo-shift-report.pdf">Download PDF</a>
      </div>

      {summary && (
        <div className="ai-narrative">
          <span className="ai-tag">AI SHIFT SUMMARY</span>
          <p>{summary.narrative}</p>
          {(summary.quality_deviations_note || summary.safety_note) && (
            <p className="muted small">
              {summary.quality_deviations_note} {summary.safety_note}
            </p>
          )}
        </div>
      )}

      <div className="tiles">
        <div className="tile"><span>Work steps</span><b>{r.steps}</b><small>avg {r.avg_step_s}s</small></div>
        <div className="tile"><span>Hands-on work</span><b>{r.breakdown_pct.work ?? 0}%</b></div>
        <div className="tile"><span>Search time</span><b>{r.breakdown_pct.search ?? 0}%</b><small>{f.search.count} events</small></div>
        <div className="tile"><span>Idle / waiting</span><b>{r.breakdown_pct.idle ?? 0}%</b><small>{f.idle.count} events</small></div>
        <div className="tile"><span>Recoverable value</span><b>€{(r.roi_eur_per_year_total || 0).toLocaleString()}</b><small>per station / year</small></div>
        <div className="tile red"><span>Est. lost time</span><b>{r.lost_min_per_shift}</b><small>min / shift</small></div>
      </div>

      <h3 className="sec">Top recommendations</h3>
      <ol className="replist">
        {r.recommendations.slice(0, 4).map((x, i) => (
          <li key={i}><b>{x.title}</b>: saves ~{x.saving_min_per_shift} min/shift. <span className="muted">{x.support}.</span></li>
        ))}
      </ol>

      <RootCause findings={causes} seek={seek} />

      {r.longest_step && (
        <>
          <h3 className="sec">Bottleneck</h3>
          <p>Longest step: <b>{r.longest_step.label}</b> in {r.longest_step.clip_id} at {fmt(r.longest_step.t_start)}, {r.longest_step.duration_s.toFixed(1)}s (average {r.avg_step_s}s).</p>
        </>
      )}

      <KnowledgeGraph clips={r.clips} />

      <h3 className="sec">Collaboration events</h3>
      <CollaborationScore clips={r.clips} />
      {r.collaboration_events?.length ? (
        <table className="tbl">
          <thead><tr><th>Recording</th><th>When</th><th>Duration</th><th>Type</th><th>Confidence</th><th>Signals</th></tr></thead>
          <tbody>
            {r.collaboration_events.map((e) => (
              <tr key={e.clip_id + e.t}>
                <td>{e.clip_id}</td>
                <td><a className="cite" onClick={() => seek(e.clip_id, e.t)}>▶ {fmt(e.t)}</a></td>
                <td>{e.dur}s</td>
                <td>{LABEL[e.type]}</td>
                <td>{Math.round((e.confidence || 0) * 100)}%</td>
                <td className="muted">{e.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No high-confidence collaboration events.</p>}
      <p className="muted small">Reported only when several signals agree (another person close and facing the wearer, work paused, voice activity or proximity). Never a transcript; precision is preferred over recall.</p>

      <h3 className="sec">Friction detail</h3>
      <table className="tbl">
        <thead><tr><th>Type</th><th>Events</th><th>Seconds observed</th></tr></thead>
        <tbody>
          {Object.entries(f).map(([k, v]) => (
            <tr key={k}><td>{LABEL[k]}</td><td>{v.count}</td><td>{v.seconds}</td></tr>
          ))}
        </tbody>
      </table>

      {acc && <Accuracy acc={acc} />}
      {ver && ver.total && <Verification v={ver} />}
      {metrics.length > 0 && (
        <>
          <h3 className="sec">Hand-tracking quality per clip</h3>
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
