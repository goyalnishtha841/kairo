import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import Analyze from "./views/Analyze.jsx";
import Sop from "./views/Sop.jsx";
import Impact from "./views/Impact.jsx";
import Proficiency from "./views/Proficiency.jsx";
import Skill from "./views/Skill.jsx";
import Quality from "./views/Quality.jsx";
import Report from "./views/Report.jsx";
import Compare from "./views/Compare.jsx";
import Clips from "./views/Clips.jsx";

const TABS = [
  ["analyze", "Analyze"],
  ["impact", "Impact"],
  ["proficiency", "Proficiency"],
  ["skill", "Skill Profile"],
  ["quality", "Quality"],
  ["sop", "SOP"],
  ["compare", "Compare"],
  ["report", "Shift Report"],
  ["clips", "Clips"],
];
const station = (id) => id.replace(/-[^-]+$/, "");

function Boot({ done }) {
  const lines = ["Loading timelines", "Indexing friction events", "Building station baselines", "Ranking recommendations"];
  return (
    <div className={"boot" + (done ? " out" : "")} aria-hidden={done}>
      <div className="boot-logo">◆ KAIRO</div>
      <div className="boot-sub">Workflow intelligence</div>
      <div className="boot-lines">{lines.map((l, i) => <div key={l} style={{ animationDelay: `${i * 0.18}s` }}>{l}</div>)}</div>
      <div className="boot-bar"><i /></div>
    </div>
  );
}

export default function App() {
  const [clips, setClips] = useState([]);
  const [clip, setClip] = useState(null);
  const [tab, setTab] = useState("analyze");
  const [timeline, setTimeline] = useState(null);
  const [report, setReport] = useState(null);
  const [engine, setEngine] = useState(null);
  const [error, setError] = useState(null);
  const pendingSeek = useRef(null);
  const videoRef = useRef(null);

  const loadClips = useCallback(() => {
    api.clips().then((cs) => {
      setClips(cs);
      setClip((cur) => cur || cs[0]?.clip_id || null);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    loadClips();
    api.engine().then(setEngine).catch(() => {});
  }, [loadClips]);

  useEffect(() => {
    if (clips.length) api.report(clips.map((c) => c.clip_id)).then(setReport).catch((e) => setError(e.message));
  }, [clips]);

  useEffect(() => {
    if (clip) api.timeline(clip).then(setTimeline).catch((e) => setError(e.message));
  }, [clip]);

  // seek(clipId, t): go to Analyze, switch clip if needed, jump the video. The <video> may not be
  // mounted yet (coming from another tab) or may be loading a new clip, so the target is parked in
  // pendingSeek and applied by whichever happens last: this effect or onLoadedMetadata.
  const [seekNonce, setSeekNonce] = useState(0);
  const seek = useCallback((clipId, t) => {
    pendingSeek.current = t;
    setTab("analyze");
    if (clipId) setClip(clipId);
    setSeekNonce((n) => n + 1);
  }, []);

  const onVideoReady = () => {
    const v = videoRef.current;
    if (pendingSeek.current != null && v && v.readyState >= 1) {
      v.currentTime = pendingSeek.current;
      v.play().catch(() => {});
      pendingSeek.current = null;
    }
  };
  useEffect(onVideoReady, [seekNonce, tab, timeline]);

  const byStation = useMemo(() => {
    const g = {};
    for (const c of clips) (g[station(c.clip_id)] ||= []).push(c);
    return g;
  }, [clips]);
  const current = clips.find((c) => c.clip_id === clip);
  const ready = (report && timeline) || error || (clips.length === 0 && engine);

  return (
    <div className="app">
      <Boot done={!!ready} />
      <header className="top">
        <div className="brand">
          <a href="#/" title="Kairo home" style={{ color: "inherit", textDecoration: "none" }}><span className="logo">◆</span> <b>KAIRO</b></a>
          <span className="tag">Workflow intelligence</span>
        </div>
        <nav className="tabs">
          {TABS.map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
          ))}
        </nav>
        <div className={"engine " + (engine?.engine || "")} title="Copilot engine">
          <span className="pulse" /> {{ groq: "Groq · gpt-oss-120b", claude: "Claude", rules: "Rules engine" }[engine?.engine] || "…"}
        </div>
      </header>

      <div className="cliprow">
        <label className="clipsel">
          <span className="muted">Recording</span>
          <select value={clip || ""} onChange={(e) => setClip(e.target.value)} aria-label="Recording">
            {Object.entries(byStation).map(([st, cs]) => (
              <optgroup key={st} label={`Station ${st}`}>
                {cs.map((c) => <option key={c.clip_id} value={c.clip_id}>{c.clip_id} · {c.friction_events} friction</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        {current && (
          <div className="live">
            <span><b>{current.steps}</b> steps</span>
            <span><b>{current.friction_events}</b> friction events</span>
            {current.metrics?.detection_rate_any_hand != null && <span><b>{Math.round(current.metrics.detection_rate_any_hand * 100)}%</b> frames with hands</span>}
          </div>
        )}
        {report && <span className="muted right">Shift view: {report.observed_min} min across {report.clips.length} recordings · {Object.keys(byStation).length} stations</span>}
      </div>

      {error && <div className="error">Backend error: {error}. Is <code>uvicorn server.app:app --port 8000</code> running?</div>}
      {!clips.length && !error && tab !== "clips" && (
        <div className="empty">No processed clips yet. Open the <a className="cite" onClick={() => setTab("clips")}>Clips</a> tab to upload or process a video.</div>
      )}

      <main key={tab} className="view">
        {tab === "analyze" && timeline && (
          <Analyze clip={clip} timeline={timeline} videoRef={videoRef} onVideoReady={onVideoReady}
                   seek={seek} clips={clips.map((c) => c.clip_id)} />
        )}
        {tab === "impact" && report && <Impact report={report} seek={seek} />}
        {tab === "proficiency" && clip && <Proficiency clip={clip} seek={seek} setClip={setClip} />}
        {tab === "skill" && clip && <Skill clip={clip} seek={seek} setClip={setClip} />}
        {tab === "quality" && clip && <Quality clip={clip} clips={clips.map((c) => c.clip_id)} seek={seek} setClip={setClip} />}
        {tab === "sop" && timeline && <Sop clip={clip} timeline={timeline} seek={seek} clips={clips.map((c) => c.clip_id)} />}
        {tab === "compare" && clips.length > 0 && <Compare clips={clips} seek={seek} />}
        {tab === "report" && report && <Report report={report} clips={clips} seek={seek} />}
        {tab === "clips" && (
          <Clips onProcessed={loadClips} metrics={Object.fromEntries(clips.map((c) => [c.clip_id, c.metrics]))} />
        )}
      </main>
    </div>
  );
}
