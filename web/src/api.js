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
  shiftSummary: (clips) => fetch(`/api/shift-summary?clips=${clips.join(",")}`).then(j),
  rootCause: (clips) => fetch(`/api/root-cause?clips=${clips.join(",")}`).then(j),
  safety: (clip) => fetch(`/api/safety?clip=${encodeURIComponent(clip)}`).then(j),
  search: (query, clips) =>
    fetch("/api/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, clips }) }).then(j),
  attention: (clip) => fetch(`/api/attention?clip=${encodeURIComponent(clip)}`).then(j),
  digitalTwin: (clip, shiftStart) =>
    fetch(`/api/digital-twin?clip=${encodeURIComponent(clip)}` + (shiftStart ? `&shift_start=${shiftStart}` : "")).then(j),
  collaborationScore: (clips) => fetch(`/api/collaboration-score?clips=${clips.join(",")}`).then(j),
  drift: (clip) => fetch(`/api/drift?clip=${encodeURIComponent(clip)}`).then(j),
  knowledgeGraph: (question, clips) =>
    fetch(`/api/knowledge-graph?question=${encodeURIComponent(question)}&clips=${clips.join(",")}`).then(j),
  memory: (label, clips) => fetch(`/api/memory?label=${encodeURIComponent(label)}&clips=${clips.join(",")}`).then(j),
  sopCompliance: (clipId, expectedSteps, mandatory) =>
    fetch("/api/sop-compliance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_id: clipId, expected_steps: expectedSteps, mandatory }),
    }).then(j),
  startHighlightReel: (clips, mode, maxClips) =>
    fetch("/api/highlight-reel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips, mode, max_clips: maxClips }),
    }).then(j),
  highlightReelStatus: (jobId) => fetch(`/api/highlight-reel/${jobId}`).then(j),
  highlightReelVideo: (jobId) => `/api/highlight-reel/${jobId}/video`,
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
  idle: "Waiting",
  hesitation: "Pausing",
  extra_reach: "Extra reaching",
  reattempt: "Picking up again",
  collaboration: "Working together",
  possible_collaboration: "Maybe working together",
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
