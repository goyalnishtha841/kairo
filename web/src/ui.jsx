import React, { useEffect, useRef, useState } from "react";

// Animated number for live counters; respects prefers-reduced-motion.
export function CountUp({ to = 0, decimals = 0, ms = 900 }) {
  const [v, setV] = useState(0);
  const raf = useRef();
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(to); return; }
    const t0 = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / ms);
      setV(to * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [to, ms]);
  return <>{v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</>;
}

// Radar chart: values 0..100 per axis, with the baseline (50) ring.
export function Radar({ data, size = 300 }) {
  const keys = Object.keys(data);
  const n = keys.length;
  const c = size / 2, R = size / 2 - 56;
  const pt = (i, v) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [c + Math.cos(a) * R * (v / 100), c + Math.sin(a) * R * (v / 100)];
  };
  const poly = (vals) => vals.map((v, i) => pt(i, v).join(",")).join(" ");
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="radar" role="img" aria-label="Workflow fingerprint radar chart">
      {[25, 50, 75, 100].map((r) => (
        <polygon key={r} points={poly(keys.map(() => r))} fill="none" stroke="var(--line)" strokeDasharray={r === 50 ? "0" : "3 4"} />
      ))}
      {keys.map((k, i) => {
        const [x, y] = pt(i, 100);
        const [lx, ly] = pt(i, 122);
        return (
          <g key={k}>
            <line x1={c} y1={c} x2={x} y2={y} stroke="var(--line)" />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" className="svgmuted">{k}</text>
          </g>
        );
      })}
      <polygon points={poly(keys.map(() => 50))} fill="none" stroke="var(--fg2)" strokeWidth="1.5" />
      <polygon points={poly(keys.map((k) => data[k]))} fill="var(--accent)" fillOpacity="0.22" stroke="var(--accent)" strokeWidth="2" />
      {keys.map((k, i) => {
        const [x, y] = pt(i, data[k]);
        return <circle key={k} cx={x} cy={y} r="3.5" fill="var(--accent)" />;
      })}
    </svg>
  );
}

// Score dial 0..100
export function Dial({ value, label }) {
  const r = 52, C = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(100, value ?? 0));
  return (
    <svg viewBox="0 0 140 140" className="dial" role="img" aria-label={`Score ${value}`}>
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--line)" strokeWidth="10" />
      <circle cx="70" cy="70" r={r} fill="none" stroke="var(--accent)" strokeWidth="10" strokeLinecap="round"
              strokeDasharray={`${(C * v) / 100} ${C}`} transform="rotate(-90 70 70)" className="dial-arc" />
      <text x="70" y="70" textAnchor="middle" className="dial-n">{value ?? "–"}</text>
      <text x="70" y="94" textAnchor="middle" className="svgmuted">{label}</text>
    </svg>
  );
}
