import React, { lazy, Suspense, useEffect, useRef, useState } from "react";
import Lenis from "lenis";
import "./landing.css";

const LiveHands = lazy(() => import("./LiveHands.jsx"));
const APP = "#/app";
const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
// Unsplash photos (Unsplash License: free for commercial use, no attribution required)
const img = (id, w = 1400) => `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=${w}&q=80`;
// Mixkit stock video (Mixkit Free License, commercial use, no attribution), stored in web/public/videos:
// hero-dark = video supplied by the team (hands assembling parts at a dark workbench),
// cta-night = mixkit 4360 "petrochemical plant lit up at night"
const HERO_VIDEO = "/videos/hero-dark.mp4";

// ---------------------------------------------------------------- motion helpers
function useReveal(root) {
  useEffect(() => {
    const els = root.current.querySelectorAll("[data-reveal]");
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { threshold: 0.18, rootMargin: "0px 0px -8% 0px" });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [root]);
}

// headline that rises word by word; *word* is set in italics
function Words({ text, as: Tag = "h2", className = "", delay = 0 }) {
  let i = 0;
  return (
    <Tag className={"lp-words " + className} data-reveal>
      {text.split("\n").map((line, li) => (
        <span key={li} className="lp-line">
          {line.split(" ").map((w, wi) => {
            const it = w.startsWith("*");
            return (
              <span key={wi} className="lp-w">
                <span style={{ transitionDelay: `${delay + 0.06 * i++}s` }}>{it ? <em>{w.replace(/\*/g, "")}</em> : w}</span>
              </span>
            );
          })}
        </span>
      ))}
    </Tag>
  );
}

function Logo({ size = 18 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path d="M12 2 22 12 12 22 2 12Z" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M12 7.5 16.5 12 12 16.5 7.5 12Z" fill="currentColor" />
    </svg>
  );
}

// ---------------------------------------------------------------- nav and hero
function Nav() {
  return (
    <header className="lp-nav">
      <nav className="lp-pill" aria-label="Main">
        <a href="#top" className="lp-brand"><Logo /> Kairo</a>
        <a href="#solutions">Solutions</a>
        <a href="#industries">Industries</a>
      </nav>
      <a href={APP} className="lp-cta">Open dashboard</a>
    </header>
  );
}

const TOASTS = [
  "Spotted 7 seconds of searching for a tool",
  "Found 26 minutes of waiting per shift",
  "Suggested a fix that saves 26 minutes a shift",
  "Rated step 5 at 87 out of 100",
  "Tracked both hands at the workbench",
];

function Hero() {
  const ref = useRef(null);
  const [toast, setToast] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setToast((t) => (t + 1) % TOASTS.length), 2800);
    let raf;
    const tick = () => {
      const el = ref.current;
      if (el) {
        const r = el.getBoundingClientRect();
        el.style.setProperty("--p", Math.min(1, Math.max(0, -r.top / (r.height - window.innerHeight))).toFixed(4));
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => { clearInterval(id); cancelAnimationFrame(raf); };
  }, []);
  return (
    <section className="lp-hero" ref={ref} id="top">
      <div className="lp-hero-sticky">
        <div className="lp-hero-media">
          <video src={HERO_VIDEO} poster="/videos/hero-dark.jpg" autoPlay muted loop playsInline
                 onError={(e) => { e.currentTarget.style.display = "none"; }} />
          <div className="lp-hero-shade" />
          <div className="lp-hero-copy">
            <Words as="h1" text={"You run the factory.\nNot the stopwatch."} delay={0.15} />
            <p className="lp-hero-sub" data-reveal>Let Kairo watch every shift</p>
          </div>
          <div className="lp-toast" key={toast} role="status"><span className="lp-dot" /> {TOASTS[toast]}</div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- stacked cards
const STACK = [
  ["Kairo watches every shift",
   "Record work with a head-mounted camera and upload the video. Kairo follows the worker's hands and notes, second by second, when work is happening and when it isn't.",
   "1504328345606-18bbc8c9d7d1"],
  ["Spots where time slips away",
   "Searching for a tool, waiting for parts, pausing between steps. Every moment is marked, so you can jump straight to it in the video.",
   "/images/grinding-sparks.webp", "40% 40%"],
  ["Tells you what to fix first",
   "Clear, ranked suggestions, like keeping the most-used tools within reach, each with the minutes and money it saves.",
   "/images/foundry-pour.webp", "72% 50%"],
];
// an Unsplash photo id, or a path to one of our own images in web/public/images
const photoSrc = (photo) => (photo.startsWith("/") ? photo : img(photo, 1200));

function Stack() {
  const ref = useRef(null);
  useEffect(() => {
    let raf;
    const tick = () => {
      const cards = ref.current ? [...ref.current.querySelectorAll(".lp-stack-card")] : [];
      cards.forEach((card, i) => {
        const next = cards[i + 1];
        let p = 0;
        if (next) {   // how far the next card has slid over this one
          const a = card.getBoundingClientRect(), b = next.getBoundingClientRect();
          p = Math.min(1, Math.max(0, 1 - (b.top - a.top) / a.height));
        }
        card.firstChild.style.transform = `scale(${1 - 0.06 * p})`;
        card.firstChild.style.filter = `brightness(${1 - 0.25 * p})`;
      });
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <section className="lp-cream lp-stack-sec" id="solutions">
      <Words text={"An extra pair of eyes\non every workstation"} className="lp-h2 lp-center" />
      <div className="lp-stack" ref={ref}>
        {STACK.map(([h, p, photo, focus], i) => (
          <div key={h} className="lp-stack-card" style={{ top: `${90 + i * 14}px` }}>
            <div className={"lp-stack-inner" + (i % 2 ? " flip" : "")}>
              <div className="lp-stack-text">
                <span className="lp-feat-n">0{i + 1}</span>
                <h3>{h}</h3>
                <p>{p}</p>
              </div>
              <div className="lp-stack-img">
                <img src={photoSrc(photo)} alt="" loading="lazy" style={focus ? { objectPosition: focus } : undefined} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- hover panels (dark)
const PANELS = [
  ["Sees the hands", "Follows the worker's own hands, and ignores coworkers passing by.", "1557176766-618483419e3b"],
  ["Times every second", "Working, searching, walking away or waiting: every second gets a label.", "1601189571632-7761ab25fc0c"],
  ["Learns the steps", "Splits the job into steps, so the next recording can be checked against them.", "1518770660439-4636190af475"],
  ["Grades the work", "A score out of 100 for each step, with the reasons behind it.", "1598302936625-6075fbd98dd7"],
  ["Ranks the fixes", "Turns lost time into minutes per shift and euros per year, best fix first.", "1647427060118-4911c9821b82"],
];

function Panels() {
  const [open, setOpen] = useState(0);
  return (
    <section className="lp-dark lp-panels-sec">
      <Words text={"Here’s how Kairo helps, every shift"} className="lp-h2 lp-center lp-h2-sm" />
      <p className="lp-sub lp-center" data-reveal>Hover a panel to see each step Kairo takes on every video.</p>
      <div className="lp-panels" data-reveal>
        {PANELS.map(([h, p, photo], i) => (
          <button key={h} className={"lp-panel" + (open === i ? " on" : "")} onMouseEnter={() => setOpen(i)}
                  onFocus={() => setOpen(i)} onClick={() => setOpen(i)} aria-expanded={open === i}>
            <img src={img(photo, 900)} alt="" loading="lazy" />
            <span className="lp-panel-shade" />
            <span className="lp-panel-n">0{i + 1}</span>
            <span className="lp-panel-t">{h}</span>
            <span className="lp-panel-p">{p}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

const TOOLS = ["Head-mounted cameras", "Phone videos", "MP4 files", "Your laptop", "Your own servers", "Spreadsheets",
  "AI assistant", "Shift reports"];

function Marquee() {
  return (
    <section className="lp-cream lp-marquee-sec">
      <p className="lp-eyebrow lp-center" data-reveal>Works with the cameras and tools you already use</p>
      <div className="lp-marquee" aria-label={TOOLS.join(", ")}>
        <div className="lp-track">{[...TOOLS, ...TOOLS].map((t, i) => <span key={i}>{t}</span>)}</div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- live demo
function Live() {
  return (
    <section className="lp-dark2 lp-live-sec" id="try">
      <Words text={"See what Kairo sees"} className="lp-h2 lp-center" />
      <p className="lp-sub lp-center" data-reveal>Try it with your own hands. The same hand tracking runs on every factory video.</p>
      <div data-reveal>
        <Suspense fallback={<div className="lp-live-wrap"><div className="lp-live-stage" /></div>}>
          <LiveHands />
        </Suspense>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- how it works (mock UI cards)
function HowItWorks() {
  return (
    <section className="lp-cream lp-how">
      <Words text="How Kairo works" className="lp-h2 lp-center" />
      <div className="lp-cards">
        <article className="lp-card" data-reveal>
          <div className="lp-mock">
            <div className="lp-mock-h"><span className="lp-avatar">A3</span><div><b>Assembly station 3</b><small>Morning shift · 3 min clip</small></div><span className="lp-live">Live</span></div>
            <div className="lp-tl">
              {[["w", 22], ["s", 6], ["w", 30], ["i", 9], ["w", 18], ["s", 4], ["w", 11]].map(([k, w], i) => <i key={i} className={k} style={{ flex: w }} />)}
            </div>
            <div className="lp-legend"><span className="w">Working</span><span className="s">Searching</span><span className="i">Waiting</span></div>
            <p className="lp-quote">Searching for a tool · 7 seconds <span className="lp-time">▶ 00:46</span></p>
          </div>
          <h3>Watches the video</h3>
          <p>Every second is labelled, and every lost moment is one click away in the video.</p>
        </article>
        <article className="lp-card" data-reveal style={{ transitionDelay: ".08s" }}>
          <div className="lp-mock">
            <div className="lp-mock-row"><span>Cut waiting time</span><b>26 min / shift</b></div>
            <div className="lp-bar"><i style={{ width: "83%" }} /></div>
            <div className="lp-mock-row small"><span>Waiting for parts or machines</span><span>83% sure</span></div>
            <div className="lp-mock-ok">Seen in 15 of 19 videos ✓</div>
          </div>
          <h3>Suggests the fix</h3>
          <p>Lost time becomes a short list of fixes, ranked by what they save.</p>
        </article>
        <article className="lp-card" data-reveal style={{ transitionDelay: ".16s" }}>
          <div className="lp-mock">
            <div className="lp-mock-row"><span>Step 5 · Assembly</span><b>87/100</b></div>
            <ul className="lp-checks">
              <li><span className="ok">✓</span> Faster than usual: 8 s vs 18 s</li>
              <li><span className="ok">✓</span> No wasted movement</li>
              <li><span className="warn">⚠</span> One pause while waiting <span className="lp-time">▶ 01:38</span></li>
            </ul>
          </div>
          <h3>Grades the work</h3>
          <p>Instead of just "done", each step gets a score out of 100 with the reasons.</p>
        </article>
      </div>
    </section>
  );
}

const INDUSTRIES = [
  ["Electronics", "See where hands wait for parts on every board.", "1562408590-e32931084e23"],
  ["Automotive", "Time each station on the line and find the slow step.", "1567789884554-0b844b597180"],
  ["Metalwork & welding", "Spot time lost fetching tools between welds.", "1609348632802-b952f368fc3a"],
  ["Food & packaging", "Measure every packing cycle and prove what changed.", "1652211955967-99c892925469"],
  ["Robotics & automation", "Find which manual steps are worth automating first.", "1563968743333-044cef800494"],
  ["Training new staff", "Compare a trainee's work with how the station usually runs.", "1607398027609-fbd1a06fb5d4"],
];

function Industries() {
  return (
    <section className="lp-dark lp-ind" id="industries">
      <Words text="Built for every factory floor" className="lp-h2 lp-center lp-h2-sm" />
      <p className="lp-sub lp-center" data-reveal>Kairo learns how each workstation normally runs, whatever is built there.</p>
      <div className="lp-ind-grid">
        {INDUSTRIES.map(([h, p, photo], i) => (
          <div key={h} className="lp-ind-card" data-reveal style={{ transitionDelay: `${(i % 3) * 0.07}s` }}>
            <img src={img(photo, 800)} alt="" loading="lazy" />
            <div><b>{h}</b><span>{p}</span></div>
          </div>
        ))}
      </div>
    </section>
  );
}

const FAQ = [
  ["Is Kairo spying on workers?",
   "No. Kairo looks at the workstation and the way the job flows, never at who did it. There are no names, no rankings of people, and every result is compared with how that station normally runs."],
  ["What do I need to get started?",
   "Just video. A head-mounted camera works best, but any clear video of hands at work will do. There is nothing to set up or train."],
  ["How accurate is it?",
   "We test it on videos it has never seen before, checked by people frame by frame. About 9 in 10 hands it draws are real hands, and the full numbers are in the app."],
  ["Does my video leave the factory?",
   "No. Kairo runs on an ordinary laptop on your own site. Only the optional AI assistant sends short text summaries, never video."],
  ["Can I ask it questions?",
   "Yes. Ask \"where did the worker search for tools?\" and every answer links to the exact moment in the video."],
  ["How long does it take?",
   "Upload a video and Kairo works through it in the background. Short clips are ready in a few minutes."],
];

function Faq() {
  const [open, setOpen] = useState(-1);
  return (
    <section className="lp-cream lp-faq">
      <Words text="FAQ" className="lp-h2 lp-center lp-h2-sm" />
      <div className="lp-faq-list">
        {FAQ.map(([q, a], i) => (
          // the fade-in lives on a wrapper React never re-renders: the observer adds "in" to it, and
          // toggling "on" below would otherwise wipe that class and hide the item again
          <div key={q} data-reveal>
            <div className={"lp-q" + (open === i ? " on" : "")}>
              <button onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
                {q}<span className="lp-plus" aria-hidden="true" />
              </button>
              <div className="lp-a"><div><p>{a}</p></div></div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="lp-cta-sec">
      <div className="lp-cta-card" data-reveal>
        <video src="/videos/cta-night.mp4" poster="/videos/cta-night.jpg" autoPlay muted loop playsInline
               onError={(e) => { e.currentTarget.style.display = "none"; }} />
        <div className="lp-cta-shade" />
        <div className="lp-cta-copy">
          <Words text={"A clear view of\nevery workstation"} className="lp-h2 lp-center lp-h2-lg" />
          <a href={APP} className="lp-cta lp-cta-big">Get started</a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="lp-footer">
      <div className="lp-foot-top">
        <div>
          <p className="lp-foot-h">Workflow insights for<br /><em>every factory floor</em></p>
          <a href={APP} className="lp-dark-btn">Open dashboard</a>
        </div>
        <div className="lp-foot-cols">
          <div><span className="lp-foot-label">Product</span><a href={APP}>Dashboard</a><a href="#try">Live demo</a><a href="#solutions">How it works</a></div>
          <div><span className="lp-foot-label">Industries</span><a href="#industries">Electronics</a><a href="#industries">Automotive</a><a href="#industries">Packaging</a></div>
          <div><span className="lp-foot-label">Trust</span><span>Runs on your site</span><span>No worker scoring</span><span>Tested accuracy</span></div>
        </div>
      </div>
      <div className="lp-foot-mark"><Logo size={26} /><p>© 2026 Kairo. All rights reserved.</p></div>
      <div className="lp-word-band" aria-hidden="true">
        <div className="lp-wordmark" data-reveal>
          Ka<span className="lp-i">ı<i className="lp-tittle" /></span>ro<i className="lp-orb" />
        </div>
      </div>
    </footer>
  );
}

export default function Landing() {
  const root = useRef(null);
  useReveal(root);
  useEffect(() => {
    document.title = "Kairo: see where time goes on every workstation";
    if (reduced()) return undefined;
    const lenis = new Lenis({ lerp: 0.09, smoothWheel: true, anchors: true });
    let raf;
    const loop = (t) => { lenis.raf(t); raf = requestAnimationFrame(loop); };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); lenis.destroy(); };
  }, []);
  return (
    <div className="lp" ref={root}>
      <Nav />
      <main>
        <Hero />
        <Stack />
        <Panels />
        <Marquee />
        <Live />
        <HowItWorks />
        <Industries />
        <Faq />
        <Cta />
      </main>
      <Footer />
    </div>
  );
}
