# Timeline contract (frozen at hour 0 — change only with the whole team)

Every module reads/writes this. One JSON file per clip: `outputs/<clip_id>/timeline.json`.

```json
{
  "clip_id": "mytronlabs-000003-002",
  "fps": 30.0,
  "duration_s": 120.0,
  "events": [
    {
      "id": "e0001",
      "t_start": 24.10,
      "t_end": 27.50,
      "type": "search",
      "hand": "R",
      "tool": "screwdriver",
      "zone": "left_bin",
      "step_id": 3,
      "cycle_id": 1,
      "confidence": 0.82,
      "note": "hand hovered over 2 bins without grasp"
    }
  ],
  "steps": [
    {"step_id": 3, "label": "Tighten screws", "t_start": 20.0, "t_end": 34.2, "keyframe": "frames/step3.jpg"}
  ]
}
```

## Event `type` values
| type | owner | meaning |
|---|---|---|
| `grasp` / `release` | B | hand-object contact starts / ends |
| `tool_use` | B | sustained contact with a tool |
| `step` | C | SOP step boundary (also in `steps[]`) |
| `search` | B | friction: head scanning + hover without grasp |
| `hesitation` | B | friction: hand near target, speed ~0, then grasp |
| `reattempt` | B | friction: repeated grasp/release within one step |
| `idle` | B | friction: both hands still, no contact |
| `extra_reach` | B | friction: path length / straight-line > threshold |

Friction types drive the red/yellow colouring in the UI.

`hand`: `"L" | "R" | "both" | null`. `zone`: string from the station zone map (`left_bin`, `center`, `right_bin`, ...), or null.

## Hand tracks (A → B)
`outputs/<clip_id>/hands.json`: per frame, per stable hand id:
`{"frame": 12, "t": 0.4, "hands": [{"id": "R", "score": 0.93, "lm": [[x,y,z]*21], "lm_raw": [[x,y]*21]}], "cam": {...}}`
Coordinates are normalised image coords (0..1). `lm` = smoothed, `lm_raw` = before filtering.

`cam` = head motion: `pan`/`tilt` (frame-widths/s, ~head turning), `roll` (rad/s),
`flow` (median flow, ~walking), `sharp` (Laplacian variance, low = motion blur), `ok`.

## Tool detection (unvalidated, additive)
`events/apply_tools.py` adds four optional fields to each `steps[]` entry when a station has
`events/config.py STATION_TOOLS` configured: `tool_detected` (string or null), `tool_detected_confidence`
(0-1), `tool_detected_box` (normalised `{cx,cy,w,h}` or null, the representative detection used as
SAM's box prompt), `tool_detection_note` (a fixed honesty string, or null). This is a separate field
from the existing `tool` (the VLM caption's guess) -- one unvalidated guess never silently overwrites
the other. See `perception/tools.py` for why neither is measured against held-out accuracy yet.

`events/tool_mask.py` adds two more, only for steps with a `tool_detected_box` and a saved keyframe:
`tool_mask` (a path under `frames/`, an overlay JPEG with the SAM 2 mask blended in) and
`tool_mask_note` (a fixed honesty string). A single-keyframe box-prompted SAM 2 (tiny, CPU) mask, not
the full video predictor with memory propagation -- and it inherits the upstream box's own
uncertainty, so it is never shown without the same "unvalidated" framing.
