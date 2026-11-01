import React, { useState } from "react";
import { api, fmt, LABEL } from "../api.js";

const EXAMPLES = [
  "Where did workers search for tools?",
  "Clips where workers struggled",
  "When was someone waiting?",
  "Who asked for help?",
  "Two-handed assembly",
];
const TONE = { search: "red", transit: "red", collaboration: "blue", possible_collaboration: "blue", step: "step" };
const NAME = { ...LABEL, step: "Work step", reattempt: "Repeated grasp" };

export default function Search({ clips, seek }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const run = (query) => {
    const text = (query ?? q).trim();
    if (!text) return;
    setQ(text); setBusy(true); setErr(null);
    api.search(text, clips).then(setRes).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };
  const byClip = res ? res.hits.reduce((n, h) => ((n[h.clip_id] = (n[h.clip_id] || 0) + 1), n), {}) : {};
  return (
    <div className="search">
      <form className="srch" onSubmit={(e) => { e.preventDefault(); run(); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about the footage in plain words…" aria-label="Search the footage" />
        <button className="ask-btn" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
      </form>
      <div className="srch-ex">
        {EXAMPLES.map((x) => <button key={x} onClick={() => run(x)}>{x}</button>)}
      </div>
      {err && <div className="error">{err}</div>}
      {res && (
        <>
          <p className="muted">
            <b style={{ color: "var(--fg)" }}>{res.count}</b> moment{res.count === 1 ? "" : "s"} in {Object.keys(byClip).length} recording
            {Object.keys(byClip).length === 1 ? "" : "s"}
            {res.matched_types.length > 0 && <> · looking for {res.matched_types.map((t) => (NAME[t] || t).toLowerCase()).join(", ")}</>}
            {res.count > Math.min(res.hits.length, 60) && ` · showing the first ${Math.min(res.hits.length, 60)}`}
          </p>
          {res.proxy_notes.map((n) => <p key={n} className="muted small">ℹ {n}</p>)}
          {res.count === 0 ? (
            <div className="empty">Nothing matched. Try words like searching, waiting, struggled, walked away, help, or a step name.</div>
          ) : (
            <div className="hits">
              {res.hits.slice(0, 60).map((h, i) => (
                <button key={i} className={"hit " + (TONE[h.type] || "")} onClick={() => seek(h.clip_id, h.t_start)}>
                  <div className="hit-h"><span>{NAME[h.type] || h.type}</span><span className="cite">▶ {fmt(h.t_start)}</span></div>
                  <b>{h.note}</b>
                  <span className="muted small">{h.clip_id}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      {!res && <p className="muted small">Search uses Kairo's own timeline, so every result is a real moment you can play. It does not listen to what people say.</p>}
    </div>
  );
}
