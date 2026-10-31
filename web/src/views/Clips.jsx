import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const STATE = { queued: "Queued", running: "Processing…", done: "Done", failed: "Failed" };

export default function Clips({ onProcessed, metrics }) {
  const [raw, setRaw] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState(null);
  const fileRef = useRef(null);
  const doneSeen = useRef(new Set());

  const refresh = () => api.raw().then((r) => {
    setRaw(r);
    // tell the app when a job finishes so the clip list / report reload
    for (const c of r) {
      if (c.job?.state === "done" && !doneSeen.current.has(c.clip_id)) {
        doneSeen.current.add(c.clip_id);
        onProcessed();
      }
    }
  }).catch((e) => setErr(e.message));

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  const process = (id) => api.process(id).then(refresh).catch((e) => setErr(e.message));
  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try { await api.upload(f); await refresh(); } catch (x) { setErr(x.message); }
    setUploading(false);
    fileRef.current.value = "";
  };

  const pending = raw.filter((c) => !c.processed);
  return (
    <div className="clips">
      <div className="cmp-h">
        <div>
          <h2>Clips</h2>
          <p className="muted">Upload a new egocentric video or process downloaded clips. Each runs: hand tracking → head motion → timeline → SOP captions → web video.</p>
        </div>
        <div className="row">
          <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,video/*" onChange={upload} hidden />
          <button className="ask-btn" disabled={uploading} onClick={() => fileRef.current.click()}>{uploading ? "Uploading…" : "Upload video"}</button>
          {pending.length > 0 && <button className="ghost" onClick={() => pending.forEach((c) => process(c.clip_id))}>Process all ({pending.length})</button>}
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      <table className="tbl">
        <thead><tr><th>Clip</th><th>Size</th><th>Status</th><th>Hands found</th><th>Tracking FPS</th><th></th></tr></thead>
        <tbody>
          {raw.map((c) => {
            const m = metrics[c.clip_id];
            const st = c.job?.state;
            return (
              <tr key={c.clip_id}>
                <td>{c.clip_id}</td>
                <td>{c.size_mb} MB</td>
                <td>
                  {st && st !== "done" ? <span className={"pill " + (st === "failed" ? "bad" : "warn")}>{STATE[st]}</span>
                    : c.processed ? <span className="pill ok">Processed</span> : <span className="muted">Not processed</span>}
                  {c.job?.error && <small className="muted"> {c.job.error}</small>}
                </td>
                <td>{m ? `${Math.round(m.detection_rate_any_hand * 100)}%` : "–"}</td>
                <td>{m ? m.processing_fps : "–"}</td>
                <td>
                  {!(st === "queued" || st === "running") && (
                    <button className="ghost sm" onClick={() => process(c.clip_id)}>{c.processed ? "Re-process" : "Process"}</button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">Processing runs on this laptop's CPU (~2 min per 3-min clip), one clip at a time.</p>
    </div>
  );
}
