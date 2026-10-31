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
`{"frame": 12, "t": 0.4, "hands": [{"id": "R", "score": 0.93, "lm": [[x,y,z]*21], "lm_raw": [[x,y]*21]}]}`
Coordinates are normalised image coords (0..1). `lm` = smoothed, `lm_raw` = before filtering.
