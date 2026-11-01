import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, COLOR, fmt, LABEL } from "../api.js";
import Copilot from "./Copilot.jsx";

const BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const HAND_COLOR = { L: "#ff8a3d", R: "#ffd2b0" };

function useHandOverlay(clip, videoRef, canvasRef, enabled) {
  const [track, setTrack] = useState(null);
  useEffect(() => { setTrack(null); api.hands(clip).then(setTrack).catch(() => {}); }, [clip]);
  useEffect(() => {
    let raf;
    const draw = () => {
      const v = videoRef.current, c = canvasRef.current;
      if (v && c) {
        const ctx = c.getContext("2d");
        c.width = v.clientWidth; c.height = v.clientHeight;
        ctx.clearRect(0, 0, c.width, c.height);
        if (enabled && track && track.frames.length) {
          // binary search nearest processed frame
          const t = v.currentTime, fr = track.frames;
          let lo = 0, hi = fr.length - 1;
          while (lo < hi) { const m = (lo + hi) >> 1; if (fr[m][0] < t) lo = m + 1; else hi = m; }
          const f = fr[lo];
          if (f && Math.abs(f[0] - t) < 0.2) {
            for (const [id, lm] of f[1]) {
              ctx.strokeStyle = HAND_COLOR[id]; ctx.lineWidth = 2.5;
              for (const [a, b] of BONES) {
                ctx.beginPath();
                ctx.moveTo(lm[a][0] * c.width, lm[a][1] * c.height);
                ctx.lineTo(lm[b][0] * c.width, lm[b][1] * c.height);
                ctx.stroke();
              }
              ctx.fillStyle = "#fff";
              for (const p of lm) { ctx.beginPath(); ctx.arc(p[0] * c.width, p[1] * c.height, 2.5, 0, 7); ctx.fill(); }
              ctx.font = "600 13px Inter"; ctx.fillStyle = HAND_COLOR[id];
              ctx.fillText(id === "L" ? "Left" : "Right", lm[0][0] * c.width + 8, lm[0][1] * c.height + 16);
            }
          }
        }
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [track, enabled, videoRef, canvasRef]);
}

// Live safety alert: predicted (not just detected) risk, surfaced the moment playback reaches a
// forecasted unsafe-reach timestamp (events/safety.py), with a visible flash and an audible beep --
// the predictive, felt version of the static Safety panel in Fixes & safety.
function useSafetyAlert(clip, now) {
  const [forecasts, setForecasts] = useState([]);
  const [active, setActive] = useState(null);
  const firedRef = useRef(new Set());
  const audioCtxRef = useRef(null);

  useEffect(() => {
    setForecasts([]);
    setActive(null);
    firedRef.current = new Set();
    api.safety(clip).then((r) => setForecasts(r.configured ? r.forecasts : [])).catch(() => {});
  }, [clip]);

  const beep = () => {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      const ctx = audioCtxRef.current || (audioCtxRef.current = new Ctx());
      const t0 = ctx.currentTime;
      for (let i = 0; i < 2; i++) {
        const osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.type = "square"; osc.frequency.value = 880;
        const s = t0 + i * 0.26;
        gain.gain.setValueAtTime(0.0001, s);
        gain.gain.exponentialRampToValueAtTime(0.22, s + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, s + 0.18);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(s); osc.stop(s + 0.2);
      }
    } catch { /* audio isn't available (autoplay policy, no AudioContext) -- the visual flash still shows */ }
  };

  useEffect(() => {
    const ALERT_WINDOW_S = 1.2;
    const hit = forecasts.find((f) => now >= f.t && now < f.t + ALERT_WINDOW_S);
    if (hit && !firedRef.current.has(hit.t)) {
      firedRef.current.add(hit.t);
      setActive(hit);
      beep();
      setTimeout(() => setActive((a) => (a === hit ? null : a)), 3500);
    }
    for (const t of firedRef.current) if (t > now + 2) firedRef.current.delete(t); // allow re-trigger on seek-back
  }, [now, forecasts]);

  return active;
}

function FrictionTimeline({ timeline, now, onSeek }) {
  const D = timeline.duration_s || 1;
  const friction = timeline.events.filter((e) => e.severity !== "green");
  const pct = (t) => `${(100 * t) / D}%`;
  const click = (ev) => {
    const r = ev.currentTarget.getBoundingClientRect();
    onSeek(((ev.clientX - r.left) / r.width) * D);
  };
  return (
    <div className="ftl">
      <div className="ftl-bar" onClick={click} title="Click to jump">
        {timeline.states.map((s, i) => (
          <div key={i} className="ftl-seg" style={{ left: pct(s.t_start), width: pct(s.t_end - s.t_start), background: COLOR[s.state] }}
               title={`${LABEL[s.state]} ${fmt(s.t_start)}–${fmt(s.t_end)}`} />
        ))}
        <div className="ftl-now" style={{ left: pct(now) }} />
      </div>
      <div className="ftl-marks">
        {friction.filter((e) => ["hesitation", "extra_reach", "reattempt"].includes(e.type)).map((e) => (
          <div key={e.id} className="ftl-mark" style={{ left: pct(e.t_start) }} title={`${LABEL[e.type]}: ${e.note}`}
               onClick={() => onSeek(e.t_start)} />
        ))}
        {timeline.events.filter((e) => e.severity === "blue").map((e) => (
          <div key={e.id} className={"ftl-collab" + (e.type === "possible_collaboration" ? " possible" : "")}
               style={{ left: pct(e.t_start), width: pct(e.t_end - e.t_start) }}
               title={`${LABEL[e.type]} (confidence ${Math.round(e.confidence * 100)}%): ${e.note}`} onClick={() => onSeek(e.t_start)} />
        ))}
      </div>
      <div className="ftl-steps">
        {timeline.steps.map((s) => (
          <div key={s.step_id} className="ftl-step" style={{ left: pct(s.t_start), width: pct(s.t_end - s.t_start) }}
               onClick={() => onSeek(s.t_start)} title={`${s.label} · ${s.duration_s}s`}>{s.step_id}</div>
        ))}
      </div>
      <div className="legend">
        {["work", "search", "transit", "idle"].map((k) => (
          <span key={k}><i style={{ background: COLOR[k] }} />{LABEL[k]}</span>
        ))}
        <span><i className="dot" />Small hold-ups (pausing, extra reaching, picking up again)</span>
        <span><i style={{ background: "var(--blue)" }} />Working together</span>
        <span className="muted">Numbers = steps of the job</span>
      </div>
    </div>
  );
}

function Attention({ clip }) {
  const [hm, setHm] = useState(null);
  useEffect(() => { setHm(null); api.attention(clip).then(setHm).catch(() => {}); }, [clip]);
  if (!hm) return null;
  const rows = Object.entries(hm.pct).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const ZONE_LABEL = { machine: "Machine / work", tool_search_left: "Tool search (left)",
    tool_search_center: "Tool search (center)", tool_search_right: "Tool search (right)",
    colleague: "Another person", floor_or_away: "Away / waiting" };
  const ZONE_COLOR = { machine: "var(--green)", tool_search_left: "var(--red)", tool_search_center: "var(--red)",
    tool_search_right: "var(--red)", colleague: "var(--blue)", floor_or_away: "var(--amber)" };
  return (
    <div className="panel attention">
      <div className="panel-h"><h3>Where the worker looked</h3><span className="muted">from head direction</span></div>
      <div className="stack">
        {rows.map(([k, v]) => <div key={k} style={{ width: `${v}%`, background: ZONE_COLOR[k] }} title={`${ZONE_LABEL[k] || k} ${v}%`} />)}
      </div>
      <div className="legend">
        {rows.map(([k, v]) => <span key={k}><i style={{ background: ZONE_COLOR[k] }} />{ZONE_LABEL[k] || k} {v}%</span>)}
      </div>
      <p className="muted small">
        From hand visibility, head scanning and collaboration signals, not gaze tracking.
        {hm.not_detected.length > 0 && ` Not detected: ${hm.not_detected.join(", ")}.`}
      </p>
    </div>
  );
}

function DigitalTwin({ clip, seek }) {
  const [open, setOpen] = useState(false);
  const [dt, setDt] = useState(null);
  useEffect(() => { if (open && !dt) api.digitalTwin(clip).then(setDt).catch(() => {}); }, [open, clip]);
  useEffect(() => { setDt(null); }, [clip]);
  return (
    <div className="panel twin">
      <div className="panel-h" style={{ cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <h3>The story of this video</h3><span className="muted">{open ? "hide" : "show"} ▾</span>
      </div>
      {open && !dt && <div className="muted small pad">Loading…</div>}
      {open && dt && (
        <ol className="twin-list">
          {dt.timeline.map((e, i) => (
            <li key={i}>
              <a className="cite" onClick={() => seek(clip, e.t)}>▶ {e.t_label}</a>
              <b>{e.event}</b><span className="muted">{e.detail}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function Analyze({ clip, timeline, videoRef, onVideoReady, seek, clips }) {
  const canvasRef = useRef(null);
  const [overlay, setOverlay] = useState(true);
  const [now, setNow] = useState(0);
  const [filter, setFilter] = useState("all");
  useHandOverlay(clip, videoRef, canvasRef, overlay);

  const friction = useMemo(() => timeline.events.filter((e) => e.severity !== "green"), [timeline]);
  const shown = filter === "all" ? friction : friction.filter((e) => e.type === filter);
  const totals = useMemo(() => {
    const t = {};
    for (const s of timeline.states) t[s.state] = (t[s.state] || 0) + s.t_end - s.t_start;
    return t;
  }, [timeline]);
  const active = friction.find((e) => now >= e.t_start && now <= e.t_end);
  const safetyAlert = useSafetyAlert(clip, now);

  return (
    <div className="analyze">
      <section className="left">
        <div className={"player" + (safetyAlert ? " safety-alert" : "")}>
          <video ref={videoRef} src={api.video(clip)} controls muted playsInline
                 onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} onLoadedMetadata={onVideoReady} />
          <canvas ref={canvasRef} />
          {active && (
            <div className={"callout " + active.severity}>
              <b>{LABEL[active.type]}</b> · {(active.t_end - active.t_start).toFixed(1)}s
              <div>{active.note}</div>
            </div>
          )}
          {safetyAlert && (
            <div className="safety-flash" role="alert">
              <b>⚠ Unsafe reach risk</b>
              <div>{Math.round(safetyAlert.probability_next_window * 100)}% chance in the next {safetyAlert.window_s}s</div>
            </div>
          )}
        </div>
        <div className="row between">
          <label className="toggle"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Show hand tracking</label>
          <div className="kpis">
            {Object.entries(totals).map(([k, v]) => (
              <span key={k} className="kpi"><i style={{ background: COLOR[k] }} />{LABEL[k]} <b>{Math.round((100 * v) / timeline.duration_s)}%</b></span>
            ))}
          </div>
        </div>
        <FrictionTimeline timeline={timeline} now={now} onSeek={(t) => seek(clip, t)} />
      </section>

      <section className="right">
        <div className="panel events">
          <div className="panel-h">
            <h3>Moments <span className="muted">({friction.length})</span></h3>
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All</option>
              {["search", "transit", "idle", "hesitation", "extra_reach", "reattempt", "collaboration", "possible_collaboration"].map((k) => <option key={k} value={k}>{LABEL[k]}</option>)}
            </select>
          </div>
          <div className="evlist">
            {shown.map((e) => (
              <button key={e.id} className={"ev " + e.severity + (active?.id === e.id ? " on" : "")} onClick={() => seek(clip, e.t_start)}>
                <span className="t">{fmt(e.t_start)}</span>
                <span className="body"><b>{LABEL[e.type]}</b> {(e.t_end - e.t_start).toFixed(1)}s<small>{e.note}</small></span>
              </button>
            ))}
            {!shown.length && <div className="muted pad">Nothing here.</div>}
          </div>
        </div>
        <Attention clip={clip} />
        <DigitalTwin clip={clip} seek={seek} />
        <Copilot clips={clips} seek={seek} />
      </section>
    </div>
  );
}
