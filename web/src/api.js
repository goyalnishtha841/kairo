const j = (r) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
};

export const api = {
  clips: () => fetch("/api/clips").then(j),
  timeline: (id) => fetch(`/api/clips/${id}/timeline`).then(j),
  hands: (id) => fetch(`/api/clips/${id}/hands`).then(j),
  report: (clips) => fetch(`/api/report?clips=${clips.join(",")}`).then(j),
  engine: () => fetch("/api/engine").then(j),
  ask: (question, clips) =>
    fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, clips }),
    }).then(j),
  compare: (ref, target) => fetch(`/api/compare?ref=${encodeURIComponent(ref)}&target=${encodeURIComponent(target)}`).then(j),
  raw: () => fetch("/api/raw").then(j),
  accuracy: () => fetch("/api/accuracy").then(j),
  verification: () => fetch("/api/verification").then(j),
  proficiency: (clip) => fetch(`/api/proficiency?clip=${encodeURIComponent(clip)}`).then(j),
  quality: (clip, ref) => fetch(`/api/quality?clip=${encodeURIComponent(clip)}&ref=${encodeURIComponent(ref || "")}`).then(j),
  skill: (clip) => fetch(`/api/skill?clip=${encodeURIComponent(clip)}`).then(j),
  simulate: (clip, type) => fetch(`/api/simulate?clip=${encodeURIComponent(clip)}&friction_type=${type}`).then(j),
  process: (id) => fetch(`/api/process/${encodeURIComponent(id)}`, { method: "POST" }).then(j),
  upload: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch("/api/upload", { method: "POST", body: fd }).then(j);
  },
  video: (id) => `/media/${id}/web.mp4`,
  frame: (id, name) => `/media/${id}/frames/${name.replace(/^frames\//, "")}`,
};

export const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export const LABEL = {
  work: "Working",
  search: "Searching",
  transit: "Walking away",
  idle: "Idle / waiting",
  hesitation: "Hesitation",
  extra_reach: "Extra reach",
  reattempt: "Repeated correction",
  collaboration: "Collaboration",
  possible_collaboration: "Possible collaboration",
};

export const COLOR = {
  work: "var(--green)",
  search: "var(--red)",
  transit: "var(--red2)",
  idle: "var(--amber)",
  hesitation: "var(--amber)",
  extra_reach: "var(--amber)",
  reattempt: "var(--amber)",
  collaboration: "var(--blue)",
  possible_collaboration: "var(--blue)",
};
