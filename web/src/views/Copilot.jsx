import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const SUGGEST = [
  "Where was time lost?",
  "Which fix saves the most time?",
  "Is this video different from usual?",
  "When did people work together?",
];
const CITE = /\[([\w.-]+)@(\d{1,2}):(\d{2})\]/g;

// renders text with [clip@mm:ss] citations as seek links and **bold**
export function Rich({ text, seek }) {
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

const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;

// mic input: live interim transcript while held, auto-submits the final result
function useVoiceInput(onFinal) {
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);

  const start = (onInterim) => {
    if (!SpeechRec || listening) return;
    const rec = new SpeechRec();
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      const isFinal = e.results[e.results.length - 1].isFinal;
      if (isFinal) onFinal(text.trim());
      else onInterim(text);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  };
  const stop = () => recRef.current?.stop();
  return { listening, supported: !!SpeechRec, start, stop };
}

// strips citations/markdown before speaking -- "[clip@00:45]" read aloud is useless noise
function speakable(text) {
  return text.replace(CITE, "").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/\s+/g, " ").trim();
}

export default function Copilot({ clips, seek }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [speak, setSpeak] = useState(false);
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
      if (speak && window.speechSynthesis) {
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(speakable(r.answer)));
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: "ai", text: `Error: ${e.message}` }]);
    }
    setBusy(false);
  };

  const voice = useVoiceInput((finalText) => { setQ(""); send(finalText); });
  const toggleMic = () => voice.listening ? voice.stop() : voice.start(setQ);

  return (
    <div className="panel copilot">
      <div className="panel-h">
        <h3>Copilot</h3>
        <span className="row" style={{ gap: 10 }}>
          {!!window.speechSynthesis && (
            <label className="toggle small" title="Read answers aloud">
              <input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} /> Speak
            </label>
          )}
          <span className="muted">answers only from the timeline</span>
        </span>
      </div>
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
        <input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder={voice.listening ? "Listening…" : "Ask about this station…"} />
        {voice.supported && (
          <button type="button" className={"mic" + (voice.listening ? " on" : "")} onClick={toggleMic}
                  title={voice.listening ? "Stop listening" : "Ask by voice"} aria-label="Ask by voice">🎤</button>
        )}
        <button disabled={busy}>Ask</button>
      </form>
    </div>
  );
}
