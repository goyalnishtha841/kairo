import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const SUGGEST = [
  "Why is this workstation inefficient?",
  "Where did the worker search for tools?",
  "Which step took the longest?",
  "What should we change?",
];
const CITE = /\[([\w.-]+)@(\d{1,2}):(\d{2})\]/g;

// renders text with [clip@mm:ss] citations as seek links and **bold**
function Rich({ text, seek }) {
  const parts = [];
  let last = 0, m;
  CITE.lastIndex = 0;
  while ((m = CITE.exec(text))) {
    parts.push(text.slice(last, m.index));
    const [, clip, mm, ss] = m;
    const t = +mm * 60 + +ss;
    parts.push(<a key={m.index} className="cite" onClick={() => seek(clip, t)}>▶ {mm}:{ss}</a>);
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return parts.map((p, i) => typeof p === "string"
    ? p.split(/(\*\*[^*]+\*\*)/).map((s, k) => s.startsWith("**") ? <b key={`${i}-${k}`}>{s.slice(2, -2)}</b> : s)
    : p);
}

export default function Copilot({ clips, seek }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  // scroll only the chat box (not the page); braces keep the effect from returning a value
  useEffect(() => {
    const box = end.current?.parentElement;
    if (box) box.scrollTop = box.scrollHeight;
  }, [msgs, busy]);

  const send = async (text) => {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    setQ("");
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setBusy(true);
    try {
      const r = await api.ask(question, clips);
      setMsgs((m) => [...m, { role: "ai", text: r.answer, engine: r.engine }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: `Error: ${e.message}` }]);
    }
    setBusy(false);
  };

  return (
    <div className="panel copilot">
      <div className="panel-h"><h3>Copilot</h3><span className="muted">answers only from the timeline</span></div>
      <div className="msgs">
        {!msgs.length && (
          <div className="suggest">
            {SUGGEST.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={"msg " + m.role}>
            <Rich text={m.text} seek={seek} />
            {m.engine && <span className="eng">{m.engine}</span>}
          </div>
        ))}
        {busy && <div className="msg ai muted">Reading the timeline…</div>}
        <div ref={end} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="ask">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this station…" />
        <button disabled={busy}>Ask</button>
      </form>
    </div>
  );
}
