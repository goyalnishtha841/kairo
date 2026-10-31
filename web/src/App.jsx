import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Analyze from "./views/Analyze.jsx";
import Sop from "./views/Sop.jsx";
import Layout from "./views/Layout.jsx";
import Report from "./views/Report.jsx";

const TABS = [
  ["analyze", "Analyze"],
  ["sop", "SOP"],
  ["layout", "Layout & Savings"],
  ["report", "Shift Report"],
];

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

  useEffect(() => {
    api.clips().then((cs) => {
      setClips(cs);
      if (cs.length) setClip(cs[0].clip_id);
    }).catch((e) => setError(e.message));
    api.engine().then(setEngine).catch(() => {});
  }, []);

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

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">◆</span> <b>Kairo</b>
          <span className="tag">Process Improvement Copilot</span>
        </div>
        <nav className="tabs">
          {TABS.map(([k, label]) => (
            <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>
          ))}
        </nav>
        <div className={"engine " + (engine?.engine || "")} title="Copilot engine">
          ● {{ groq: "Groq · gpt-oss-120b", claude: "Claude", rules: "Rules engine" }[engine?.engine] || "…"}
        </div>
      </header>

      <div className="cliprow">
        <span className="muted">Clips</span>
        {clips.map((c) => (
          <button key={c.clip_id} className={"chip" + (c.clip_id === clip ? " on" : "")} onClick={() => setClip(c.clip_id)}>
            {c.clip_id}
            <span className="badge">{c.friction_events}</span>
          </button>
        ))}
        {report && <span className="muted right">Shift view: {report.observed_min} min across {report.clips.length} clips</span>}
      </div>

      {error && <div className="error">Backend error: {error}. Is <code>uvicorn server.app:app --port 8000</code> running?</div>}
      {!clips.length && !error && <div className="empty">No processed clips yet. Run <code>python pipeline.py --all</code>.</div>}

      <main>
        {tab === "analyze" && timeline && (
          <Analyze clip={clip} timeline={timeline} videoRef={videoRef} onVideoReady={onVideoReady}
                   seek={seek} clips={clips.map((c) => c.clip_id)} />
        )}
        {tab === "sop" && timeline && <Sop clip={clip} timeline={timeline} seek={seek} />}
        {tab === "layout" && report && <Layout report={report} seek={seek} />}
        {tab === "report" && report && <Report report={report} clips={clips} seek={seek} />}
      </main>
    </div>
  );
}
