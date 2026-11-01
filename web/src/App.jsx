import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import { applyTheme, initialTheme, saveTheme } from "./theme.js";
import Analyze from "./views/Analyze.jsx";
import Sop from "./views/Sop.jsx";
import Impact from "./views/Impact.jsx";
import Proficiency from "./views/Proficiency.jsx";
import Skill from "./views/Skill.jsx";
import Quality from "./views/Quality.jsx";
import Report from "./views/Report.jsx";
import Compare from "./views/Compare.jsx";
import Clips from "./views/Clips.jsx";
import Overview from "./views/Overview.jsx";
import Search from "./views/Search.jsx";

// every page: key, short name (used in sub-switches), page title, one plain sentence, follows the selected video?
const TABS = [
  ["overview", "Overview", "Today on the floor", "What happened across every video, how much time it cost, and what to fix first.", false],
  ["analyze", "Watch", "Watch a video", "Play it with hand tracking and see every second labelled: working, searching or waiting.", true],
  ["impact", "Fixes & safety", "Fixes worth making", "Changes that win back the most time, the proof behind each one, and safety risks.", false],
  ["sop", "This video", "Steps of the job", "The job split into steps, checked against your written procedure and earlier videos.", true],
  ["compare", "Compare two", "Compare two videos", "Put two videos of the same job side by side: missing, extra and slower steps.", false],
  ["quality", "Quality", "How well it was done", "A score out of 100 for the job and for each step, with the reason behind every point.", true],
  ["proficiency", "Compared with usual", "Compared with usual", "How this video compares with how the station normally runs, and whether that is changing.", true],
  ["skill", "Hand skill", "Hand skill", "Whether the hand movement looks practised or new. About the movement, never the person.", true],
  ["search", "Search", "Search the videos", "Ask in plain words, like \"where did workers look for tools\", and jump to every moment.", false],
  ["report", "Report", "Shift report", "Everything on one page, plus a PDF to share.", false],
  ["clips", "Videos", "Your videos", "Upload a video or process one you already have. Kairo works through it in the background.", false],
];
// the top bar: one button per group; groups with several pages get a small switch under the heading
const NAV = [
  ["Overview", ["overview"]], ["Watch", ["analyze"]], ["Fixes & safety", ["impact"]], ["Steps", ["sop", "compare"]],
  ["Quality", ["quality"]], ["Patterns", ["proficiency", "skill"]], ["Search", ["search"]], ["Report", ["report"]], ["Videos", ["clips"]],
];
const station = (id) => id.replace(/-[^-]+$/, "");

function Logo({ size = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path d="M12 2 22 12 12 22 2 12Z" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M12 7.5 16.5 12 12 16.5 7.5 12Z" fill="currentColor" />
    </svg>
  );
}

function ThemeSwitch({ theme, setTheme }) {
  const dark = theme === "dark";
  return (
    <button className="theme-switch" role="switch" aria-checked={dark} onClick={() => setTheme(dark ? "light" : "dark")}
            title={dark ? "Switch to light mode" : "Switch to dark mode"}>
      <span className="track"><span className="knob" aria-hidden="true">{dark ? "☾" : "☀"}</span></span>
      <span className="sr">{dark ? "Dark" : "Light"}</span>
    </button>
  );
}

function Boot({ done }) {
  const lines = ["Loading the recordings", "Finding where time was lost", "Learning how each station usually runs", "Ranking the fixes"];
  return (
    <div className={"boot" + (done ? " out" : "")} aria-hidden={done}>
      <div className="boot-logo"><Logo size={34} /> Kairo</div>
      <div className="boot-sub">Getting today's shift ready</div>
      <div className="boot-lines">{lines.map((l, i) => <div key={l} style={{ animationDelay: `${i * 0.18}s` }}>{l}</div>)}</div>
      <div className="boot-bar"><i /></div>
    </div>
  );
}

export default function App() {
  const [clips, setClips] = useState([]);
  const [clip, setClip] = useState(null);
  const [tab, setTab] = useState("overview");
  const [theme, setThemeState] = useState(initialTheme);
  const setTheme = (t) => { setThemeState(t); saveTheme(t); };
  useEffect(() => { applyTheme(theme); }, [theme]);
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
  const meta = TABS.find((t) => t[0] === tab);
  const group = NAV.find((g) => g[1].includes(tab));

  return (
    <div className="app">
      <Boot done={!!ready} />
      <header className="top">
        <div className="brand">
          <a href="#/" title="Back to the Kairo home page"><span className="logo"><Logo /></span> Kairo</a>
        </div>
        <nav className="tabs" aria-label="Dashboard">
          {NAV.map(([label, views]) => {
            const on = views.includes(tab);
            return <button key={label} className={on ? "on" : ""} onClick={() => setTab(on ? tab : views[0])} aria-current={on ? "page" : undefined}>{label}</button>;
          })}
        </nav>
        <div className={"engine " + (engine?.engine || "")} title="Which AI answers your questions">
          <span className="pulse" /> {{ groq: "AI assistant on", claude: "AI assistant on", rules: "Offline answers" }[engine?.engine] || "…"}
        </div>
        <ThemeSwitch theme={theme} setTheme={setTheme} />
      </header>

      <section className="pagehead">
        <div>
          <span className="eyebrow">{meta[4] && current ? `Station ${station(current.clip_id)}` : report ? `${report.clips.length} videos · ${Math.round(report.observed_min)} minutes watched` : "Kairo"}</span>
          <h1>{meta[2]}</h1>
          <p>{meta[3]}</p>
          {group[1].length > 1 && (
            <div className="seg" role="tablist" aria-label={group[0]}>
              {group[1].map((v) => (
                <button key={v} role="tab" aria-selected={tab === v} className={tab === v ? "on" : ""} onClick={() => setTab(v)}>
                  {TABS.find((t) => t[0] === v)[1]}
                </button>
              ))}
            </div>
          )}
        </div>
        {meta[4] && (
          <div className="cliprow">
            <label className="clipsel">
              <select value={clip || ""} onChange={(e) => setClip(e.target.value)} aria-label="Recording">
                {Object.entries(byStation).map(([st, cs]) => (
                  <optgroup key={st} label={`Station ${st}`}>
                    {cs.map((c) => <option key={c.clip_id} value={c.clip_id}>{c.clip_id} · {c.friction_events} moments lost</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
            {current && (
              <div className="live">
                <span><b>{current.steps}</b> steps</span>
                <span><b>{current.friction_events}</b> moments lost</span>
                {current.metrics?.detection_rate_any_hand != null && <span><b>{Math.round(current.metrics.detection_rate_any_hand * 100)}%</b> hands in view</span>}
              </div>
            )}
          </div>
        )}
      </section>

      {error && <div className="error">Backend error: {error}. Is <code>uvicorn server.app:app --port 8000</code> running?</div>}
      {!clips.length && !error && tab !== "clips" && (
        <div className="empty">No recordings yet. Open <a className="cite" onClick={() => setTab("clips")}>Videos</a> to upload or process one.</div>
      )}

      <main key={tab} className="view">
        {tab === "overview" && report && <Overview report={report} seek={seek} go={setTab} />}
        {tab === "search" && clips.length > 0 && <Search clips={clips.map((c) => c.clip_id)} seek={seek} />}
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
