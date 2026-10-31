"""Name SOP steps from their keyframes with a vision model (Groq Qwen, or Claude).

Writes `label` (short action) and `tool` onto each step in outputs/<clip>/timeline.json and keeps the
motion-based name in `motion_label`. Safe to re-run; skips clips already captioned unless --force.

Usage: python ai/sop_labels.py MTL-SGF00106-021 [...] [--force]
"""
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai"))
import env  # noqa: E402,F401  (loads .env)

OUT = ROOT / "outputs"
MODEL = "claude-opus-5-5"
GROQ_VISION = "qwen/qwen3.8-27b"
MAX_IMAGES = 3  # Groq's Qwen vision model accepts at most 3 images per request

PROMPT = """These are keyframes from consecutive work steps, filmed by a head-mounted camera on a
factory worker (fisheye lens; the worker's own hands are near the bottom of the frame).
For each image, in order, give a short imperative SOP step name (2-5 words, e.g. "Cut panel with
circular saw", "Align frame joint", "Fasten slat with nail gun") and the main tool in the worker's
hands (or null if none). Describe the task, never the person.
Reply with only a JSON array: [{"label": "...", "tool": "..." | null}, ...] with one entry per image."""


def _b64(clip_id, s):
    return base64.standard_b64encode((OUT / clip_id / s["keyframe"]).read_bytes()).decode()


def _parse(text):
    m = re.search(r"\[.*\]", re.sub(r"<think>.*?</think>", "", text, flags=re.S), re.S)
    try:
        return json.loads(m.group(0)) if m else []
    except json.JSONDecodeError:
        return []


def _claude(clip_id, steps):
    import anthropic

    content = []
    for i, s in enumerate(steps, 1):
        content += [{"type": "text", "text": f"Step {i}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": _b64(clip_id, s)}}]
    content.append({"type": "text", "text": PROMPT})
    resp = anthropic.Anthropic().beta.messages.create(
        model=MODEL, max_tokens=4000, messages=[{"role": "user", "content": content}],
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        return []
    return _parse("".join(b.text for b in resp.content if b.type == "text"))


def _groq(clip_id, steps):
    from groq import Groq

    client, items = Groq(max_retries=5, timeout=120), []
    for k in range(0, len(steps), MAX_IMAGES):
        batch = steps[k:k + MAX_IMAGES]
        content = [{"type": "text", "text": PROMPT}]
        for i, s in enumerate(batch, 1):
            content += [{"type": "text", "text": f"Step {i}:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(clip_id, s)}"}}]
        resp = client.chat.completions.create(model=GROQ_VISION, max_tokens=4000,
                                              messages=[{"role": "user", "content": content}])
        got = _parse(resp.choices[0].message.content or "")
        items += (got + [{}] * len(batch))[:len(batch)]  # keep alignment if the model returns too few
    return items


def caption_clip(clip_id, engine="groq", force=False):
    p = OUT / clip_id / "timeline.json"
    tl = json.loads(p.read_text())
    steps = [s for s in tl["steps"] if s.get("keyframe")]
    if not steps or (not force and all(s.get("captioned") for s in steps)):
        return 0
    items = _groq(clip_id, steps) if engine == "groq" else _claude(clip_id, steps)
    for s, it in zip(steps, items):
        if not it.get("label"):
            continue
        s.setdefault("motion_label", s["label"])
        s["label"] = str(it.get("label") or s["label"])[:60]
        tool = str(it.get("tool") or "").strip()
        s["tool"] = None if tool.lower() in ("", "null", "none", "n/a", "no tool") else tool[:40]
        s["captioned"] = True
    # propagate tool names onto events inside each step
    tools = {s["step_id"]: s.get("tool") for s in steps}
    for e in tl["events"]:
        if e.get("step_id") in tools and not e.get("tool"):
            e["tool"] = tools[e["step_id"]]
    p.write_text(json.dumps(tl, indent=1))
    return len(items)


if __name__ == "__main__":
    import copilot

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    eng = copilot.available_engine()
    for c in args:
        print(c, caption_clip(c, eng, force="--force" in sys.argv) if eng != "rules" else 0, f"steps captioned ({eng})")
