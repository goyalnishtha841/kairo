import React, { useEffect, useRef, useState } from "react";
import { api, fmt, LABEL } from "../api.js";
import { CAUSE, mins } from "./Overview.jsx";

// a root-cause finding in plain words: [what happens, why, what to try]
const cause = (f) => CAUSE[f.pattern] || [f.step_label, f.root_cause, f.fix];

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
      <h3 className="sec">Why it happens</h3>
      {findings.length ? (
        <ol className="replist">
          {findings.slice(0, 5).map((f, i) => (
            <li key={i}>
              <b>{cause(f)[0]}</b> <span className="muted">({f.clip_id})</span>: {cause(f)[1]} <span className="muted">Try: {cause(f)[2]}</span>{" "}
              {f.evidence.map((c, j) => {
                const p = citeToSeconds(c);
                return p ? <a key={j} className="cite" onClick={() => seek(f.clip_id, p.t)}>▶ {p.label}</a> : null;
              })}
            </li>
          ))}
        </ol>
      ) : <p className="muted">No repeated pattern points to a clear cause yet.</p>}
      <p className="muted small">Found from repeated patterns in the video, not guessed by AI. Every finding links to the moments behind it.</p>
    </>
  );
}

function CollaborationScore({ clips }) {
  const [cs, setCs] = useState(null);
  useEffect(() => { api.collaborationScore(clips).then(setCs).catch(() => {}); }, [clips.join(",")]);
  if (!cs || !cs.total_collaboration_events) return null;
  return (
    <div className="tiles" style={{ marginBottom: 16 }}>
      <div className="tile"><span>How often people helped</span><b>{cs.avg_help_frequency_per_hour}</b><small>times per hour, on average</small></div>
      <div className="tile"><span>Waiting for someone</span><b>{cs.total_waiting_s} s</b><small>work paused for another person</small></div>
      <div className="tile"><span>Most waiting in</span><b>{cs.clip_with_most_waiting?.slice(-6) || "–"}</b><small>video</small></div>
    </div>
  );
}

const DELAY_DIMS = [
  { k: "task", label: "Task", q: "which task causes the highest delay?" },
  { k: "friction", label: "Kind of problem", q: "which friction type causes the highest delay?" },
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
      <h3 className="sec">What causes the most delay?</h3>
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
                <thead><tr><th>{DELAY_DIMS.find((d) => d.k === dim).label}</th><th>Time lost</th></tr></thead>
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

const REEL_MODES = [
  { k: "friction", label: "Worst moments", desc: "A toolbox-talk reel of the clearest friction, worst first." },
  { k: "clean", label: "Best practice", desc: "The longest friction-free stretches -- how it should look." },
];

function HighlightReel({ clips }) {
  const [mode, setMode] = useState("friction");
  const [job, setJob] = useState(null);
  const pollRef = useRef(null);
  useEffect(() => () => clearInterval(pollRef.current), []);

  const start = () => {
    setJob(null);
    api.startHighlightReel(clips, mode, 6).then((j0) => {
      setJob(j0);
      pollRef.current = setInterval(() => {
        api.highlightReelStatus(j0.job_id).then((j1) => {
          setJob(j1);
          if (j1.state !== "queued" && j1.state !== "running") clearInterval(pollRef.current);
        }).catch(() => clearInterval(pollRef.current));
      }, 1000);
    });
  };

  const busy = job && (job.state === "queued" || job.state === "running");
  return (
    <>
      <h3 className="sec">Make a training video</h3>
      <div className="panel glass pad">
        <p className="muted small">
          Auto-cuts a short, captioned video from the moments above -- no editing. Each clip is trimmed
          from the real footage with the exact finding as its caption.
        </p>
        <div className="row" style={{ marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
          {REEL_MODES.map((m) => (
            <button key={m.k} className={"ghost sm" + (mode === m.k ? " on" : "")} onClick={() => setMode(m.k)}
                    title={m.desc}>{m.label}</button>
          ))}
          <button className="ghost" disabled={busy} onClick={start} style={{ marginLeft: "auto" }}>
            {busy ? "Generating…" : "Generate"}
          </button>
        </div>
        {job && (job.state === "done" ? (
          <>
            <video src={api.highlightReelVideo(job.job_id)} controls style={{ width: "100%", borderRadius: 10, marginTop: 6 }} />
            <p className="muted small" style={{ marginTop: 8 }}>
              {job.result.moments.length} moment{job.result.moments.length === 1 ? "" : "s"}, {job.result.duration_s}s total.{" "}
              <a className="ghost sm" style={{ textDecoration: "none" }} href={api.highlightReelVideo(job.job_id)} download="kairo-highlight-reel.mp4">Download</a>
            </p>
            {job.result.skipped.length > 0 && (
              <p className="muted small">{job.result.skipped.length} moment(s) skipped (no source video for that clip).</p>
            )}
          </>
        ) : job.state === "empty" ? (
          <p className="muted small">{job.result?.note || "No moments found for this mode."}</p>
        ) : job.state === "failed" ? (
          <p className="warn small">Failed: {job.error}</p>
        ) : (
          <p className="muted small">{job.state === "queued" ? "Queued…" : "Trimming, captioning and stitching the clips…"}</p>
        ))}
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
          <p className="muted">{date} · {r.clips.length} videos · {Math.round(r.observed_min)} minutes watched · per-shift numbers scaled to {r.shift_hours} hours</p>
        </div>
        <a className="ghost" style={{ textDecoration: "none" }}
           href={`/api/shift-report.pdf?clips=${r.clips.join(",")}&shift_hours=${r.shift_hours}`}
           download="kairo-shift-report.pdf">Download PDF</a>
      </div>

      {summary && (
        <div className="ai-narrative">
          <span className="ai-tag">SHIFT SUMMARY</span>
          <p>{summary.narrative}</p>
          {(summary.quality_deviations_note || summary.safety_note) && (
            <p className="muted small">
              {summary.quality_deviations_note} {summary.safety_note}
            </p>
          )}
        </div>
      )}

      <div className="tiles">
        <div className="tile"><span>Steps of work</span><b>{r.steps}</b><small>about {Math.round(r.avg_step_s)} s each</small></div>
        <div className="tile"><span>Hands on the work</span><b>{Math.round(r.breakdown_pct.work ?? 0)}%</b><small>of the time</small></div>
        <div className="tile"><span>Searching</span><b>{Math.round(r.breakdown_pct.search ?? 0)}%</b><small>{f.search.count} times</small></div>
        <div className="tile"><span>Waiting</span><b>{Math.round(r.breakdown_pct.idle ?? 0)}%</b><small>{f.idle.count} times</small></div>
        <div className="tile"><span>Can be won back</span><b>{mins(r.recoverable_min_per_shift)}</b><small>per shift</small></div>
        <div className="tile red"><span>Time lost</span><b>{mins(r.lost_min_per_shift)}</b><small>per shift</small></div>
      </div>

      <h3 className="sec">Fix these first</h3>
      <ol className="replist">
        {r.recommendations.slice(0, 4).map((x, i) => (
          <li key={i}><b>{x.title}</b>: saves about {Math.round(x.saving_min_per_shift)} min per shift. <span className="muted">Seen {x.evidence_stats?.events} times in {x.evidence_stats?.clips} of {x.evidence_stats?.of_clips} videos.</span></li>
        ))}
      </ol>

      <RootCause findings={causes} seek={seek} />

      {r.longest_step && (
        <>
          <h3 className="sec">Slowest step</h3>
          <p><b>{r.longest_step.label}</b> took {Math.round(r.longest_step.duration_s)} s (a step usually takes about {Math.round(r.avg_step_s)} s). <a className="cite" onClick={() => seek(r.longest_step.clip_id, r.longest_step.t_start)}>▶ {r.longest_step.clip_id.slice(-6)} {fmt(r.longest_step.t_start)}</a></p>
        </>
      )}

      <HighlightReel clips={r.clips} />

      <KnowledgeGraph clips={r.clips} />

      <h3 className="sec">When people worked together</h3>
      <CollaborationScore clips={r.clips} />
      {r.collaboration_events?.length ? (
        <table className="tbl">
          <thead><tr><th>Video</th><th>When</th><th>How long</th><th>Type</th><th>How sure</th><th>Why we think so</th></tr></thead>
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
      ) : <p className="muted">No clear moments of working together.</p>}
      <p className="muted small">Only shown when several signs agree: someone close and facing the worker, work paused, voices. Kairo never records what was said.</p>

      <details className="more">
        <summary>How accurate is Kairo? (details for engineers)</summary>
      <h3 className="sec">Lost time by kind</h3>
      <table className="tbl">
        <thead><tr><th>Kind</th><th>Times</th><th>Seconds in the video</th></tr></thead>
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
      </details>
      <p className="muted small" style={{ marginTop: 18 }}>Kairo looks at workstations and how the job flows, never at who did it.</p>
    </div>
  );
}
