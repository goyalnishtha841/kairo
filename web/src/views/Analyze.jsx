import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, COLOR, fmt, LABEL } from "../api.js";
import Copilot from "./Copilot.jsx";

const BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const HAND_COLOR = { L: "#ff9a3c", R: "#3cc8ff" };

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
        {friction.filter((e) => ["hesitation", "extra_reach"].includes(e.type)).map((e) => (
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
        <span><i className="dot" />Hesitation / extra reach</span>
        <span><i style={{ background: "var(--blue)" }} />Collaboration</span>
        <span className="muted">Numbered blocks = SOP steps</span>
      </div>
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

  return (
    <div className="analyze">
      <section className="left">
        <div className="player">
          <video ref={videoRef} src={api.video(clip)} controls muted playsInline
                 onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} onLoadedMetadata={onVideoReady} />
          <canvas ref={canvasRef} />
          {active && (
            <div className={"callout " + active.severity}>
              <b>{LABEL[active.type]}</b> · {(active.t_end - active.t_start).toFixed(1)}s
              <div>{active.note}</div>
            </div>
          )}
        </div>
        <div className="row between">
          <label className="toggle"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} /> Hand tracking overlay</label>
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
            <h3>Events <span className="muted">({friction.length})</span></h3>
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All</option>
              {["search", "transit", "idle", "hesitation", "extra_reach", "collaboration", "possible_collaboration"].map((k) => <option key={k} value={k}>{LABEL[k]}</option>)}
            </select>
          </div>
          <div className="evlist">
            {shown.map((e) => (
              <button key={e.id} className={"ev " + e.severity + (active?.id === e.id ? " on" : "")} onClick={() => seek(clip, e.t_start)}>
                <span className="t">{fmt(e.t_start)}</span>
                <span className="body"><b>{LABEL[e.type]}</b> {(e.t_end - e.t_start).toFixed(1)}s<small>{e.note}</small></span>
              </button>
            ))}
            {!shown.length && <div className="muted pad">No events.</div>}
          </div>
        </div>
        <Copilot clips={clips} seek={seek} />
      </section>
    </div>
  );
}
