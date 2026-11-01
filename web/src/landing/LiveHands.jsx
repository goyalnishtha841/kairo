import React, { useEffect, useRef, useState } from "react";

// Live hand tracking in the visitor's browser, with the same MediaPipe hand model Kairo uses.
// The camera stream never leaves the page: nothing is recorded or uploaded.
// Engine and model are served by Kairo itself (web/public/mediapipe), so the demo starts in seconds and works offline.
const WASM = "/mediapipe";
const MODEL = "/mediapipe/hand_landmarker.task";
const INIT_TIMEOUT_MS = 45000;

const withTimeout = (p, ms, what) => Promise.race([p, new Promise((_, rej) =>
  setTimeout(() => rej(Object.assign(new Error(`${what} took too long`), { name: "TimeoutError" })), ms))]);

async function createModel() {
  const { FilesetResolver, HandLandmarker } = await import("@mediapipe/tasks-vision");
  const files = await FilesetResolver.forVisionTasks(WASM);
  const opts = (delegate) => ({
    baseOptions: { modelAssetPath: MODEL, delegate },
    runningMode: "VIDEO", numHands: 2,
    minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5,
  });
  try {
    return await HandLandmarker.createFromOptions(files, opts("GPU"));
  } catch {
    return HandLandmarker.createFromOptions(files, opts("CPU"));   // no WebGL on this device
  }
}
const BONES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [0, 17], [17, 18], [18, 19], [19, 20]];
const MOVING = 0.35;   // palm speed (frame widths per second) that counts as moving
const STILL_S = 1.5;   // hands still this long = waiting

function palm(lm) {
  const ids = [0, 5, 9, 13, 17];
  return [ids.reduce((a, i) => a + lm[i].x, 0) / 5, ids.reduce((a, i) => a + lm[i].y, 0) / 5];
}

export default function LiveHands() {
  const video = useRef(null);
  const canvas = useRef(null);
  const run = useRef({ stream: null, raf: 0, model: null, last: null, stillSince: null, moves: 0, moving: false });
  const [phase, setPhase] = useState("idle");   // idle | loading | live | error
  const [error, setError] = useState("");
  const [step, setStep] = useState("");
  const [stats, setStats] = useState({ hands: 0, state: "No hands in view", moves: 0, speed: 0 });

  const stop = () => {
    const r = run.current;
    cancelAnimationFrame(r.raf);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.stream = null;
    setPhase("idle");
  };
  useEffect(() => () => { stop(); run.current.model?.close(); }, []);

  const start = async () => {
    setPhase("loading");
    setError("");
    const r = run.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error("no camera API"), { name: "NoCameraApi" });
      setStep("Waiting for camera permission…");
      r.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 960, height: 540, facingMode: "user" }, audio: false });
      video.current.srcObject = r.stream;
      await video.current.play();
      if (!r.model) {
        setStep("Loading the hand model…");
        r.model = await withTimeout(createModel(), INIT_TIMEOUT_MS, "Loading the hand model");
      }
      r.last = null; r.stillSince = null; r.moves = 0; r.moving = false;
      setPhase("live");
      loop();
    } catch (e) {
      console.error("Kairo live demo:", e);
      stop();
      setPhase("error");
      const msg = {
        NotAllowedError: "Camera access was blocked. Click the camera icon in the address bar, allow it, then try again.",
        NotFoundError: "No camera was found on this device.",
        NotReadableError: "The camera is busy in another app (Zoom, Teams…). Close it and try again.",
        NoCameraApi: "This page needs a secure address (https or localhost) to use the camera.",
        TimeoutError: "The hand model is taking too long to load. Check your connection and try again.",
      }[e && e.name];
      setError(msg || `Something went wrong starting the demo (${e && e.message ? e.message : e}).`);
    }
  };

  const loop = () => {
    const r = run.current;
    const v = video.current, c = canvas.current;
    if (!r.stream || !v || !c) return;
    if (v.readyState >= 2) {
      const now = performance.now();
      const res = r.model.detectForVideo(v, now);
      const w = (c.width = v.videoWidth), h = (c.height = v.videoHeight);
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, w, h);
      let speed = 0;
      res.landmarks.forEach((lm, k) => {
        ctx.strokeStyle = k ? "#ffb27a" : "#ff8a3d";
        ctx.lineWidth = Math.max(3, w / 220);
        ctx.lineCap = "round";
        for (const [a, b] of BONES) {
          ctx.beginPath(); ctx.moveTo(lm[a].x * w, lm[a].y * h); ctx.lineTo(lm[b].x * w, lm[b].y * h); ctx.stroke();
        }
        ctx.fillStyle = "#fff";
        for (const p of lm) { ctx.beginPath(); ctx.arc(p.x * w, p.y * h, Math.max(3, w / 260), 0, 7); ctx.fill(); }
      });
      // how fast the hands move, to tell working from waiting (the same idea Kairo uses on factory video)
      const p = res.landmarks.map(palm);
      if (r.last && p.length && r.last.p.length) {
        const dt = Math.max((now - r.last.t) / 1000, 1e-3);
        speed = Math.hypot(p[0][0] - r.last.p[0][0], p[0][1] - r.last.p[0][1]) / dt;
      }
      r.last = { t: now, p };
      const movingNow = speed > MOVING;
      if (movingNow && !r.moving) r.moves += 1;
      r.moving = movingNow;
      if (!p.length || movingNow) r.stillSince = null;
      else if (r.stillSince == null) r.stillSince = now;
      const state = !p.length ? "No hands in view"
        : r.stillSince != null && now - r.stillSince > STILL_S * 1000 ? "Waiting" : "Working";
      setStats((s) => (s.hands === p.length && s.state === state && s.moves === r.moves && Math.abs(s.speed - speed) < 0.05
        ? s : { hands: p.length, state, moves: r.moves, speed }));
    }
    r.raf = requestAnimationFrame(loop);
  };

  return (
    <div className="lp-live-wrap">
      <div className={"lp-live-stage " + phase}>
        <video ref={video} playsInline muted />
        <canvas ref={canvas} />
        {phase !== "live" && (
          <div className="lp-live-cover">
            <div className="lp-live-hand" aria-hidden="true">✋</div>
            <p>{phase === "loading" ? step : phase === "error" ? error
              : "Hold your hands up to the camera and Kairo will track them, just like it does on the factory floor."}</p>
            {phase === "loading" ? <span className="lp-spinner" aria-hidden="true" />
              : <button className="lp-cta" onClick={start}>{phase === "error" ? "Try again" : "Turn on camera"}</button>}
          </div>
        )}
      </div>
      <div className="lp-live-side">
        <div className="lp-live-stat"><span>Hands in view</span><b>{phase === "live" ? stats.hands : "–"}</b></div>
        <div className="lp-live-stat"><span>Right now</span>
          <b className={"st-" + stats.state.split(" ")[0].toLowerCase()}>{phase === "live" ? stats.state : "–"}</b></div>
        <div className="lp-live-stat"><span>Movements counted</span><b>{phase === "live" ? stats.moves : "–"}</b></div>
        <p className="lp-live-note">Runs entirely in your browser. Nothing is recorded or uploaded.</p>
        {phase === "live" && <button className="lp-live-stop" onClick={stop}>Turn off camera</button>}
      </div>
    </div>
  );
}
