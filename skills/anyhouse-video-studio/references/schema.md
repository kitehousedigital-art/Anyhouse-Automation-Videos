# Field reference

Canvas: **1080 x 1920**, 30 fps. Positions are fractions of the canvas unless marked px.

## Video (`content/ideas.json` -> `videos[]`)
| key | type | notes |
|---|---|---|
| `id` | string | file name of the render (`output/<id>.mp4`); slug `[a-z0-9_]` |
| `template` | string | layout id (`list_layouts`) - required |
| `header` | string | headline; newline = line break |
| `lines` | (string \| object)[] | on-screen lines; object form below |
| `header_style` | object | per-element overrides for the headline |
| `interval` | seconds | per-line gap (stack/single); layout default otherwise |
| `hold` | seconds | how long the last line stays |
| `header_delay` | seconds | gap between headline and first line |
| `background` | string | part of a clip file name in `inbox/` |
| `tags` | string[] | matched against clip file names (e.g. `utrecht` matches `utrecht_canal.mp4`) |
| `cta` | string | extra end card text (`brand.json` can enable a global one) |
| `status` | `"verify"` | figures need checking before posting |
| `caption`, `hashtags` | string | for posting; not rendered |

Background selection order: `background` name -> first `tag` match -> rotate through clips by video index.

## Element overrides (a line object, or `header_style`)
Text & look: `text`, `font` (file in `fonts/`), `size` (px; omit = auto-fit), `color` (#RRGGBB[AA]), `align` (left|center|right), `upper` (bool), `line_spacing` (1.0-2.5),
`stroke` (outline px), `stroke_color`.
Box: `bg_mode` (`none` | `line` per line | `row` one block), `bg_color`, `bg_opacity` (0-1), `bg_radius` (px).
Shadow: `shadow_on` (bool), `shadow_color`, `shadow_blur`, `shadow_dy`.
Neon: `glow_color`, `glow_r` (4-60).
Transform: `opacity` (0-1), `rotate` (deg, -45..45), `dx`, `dy` (px offsets).
Timing: `anim` (`fade` default | `none` | `slide_up` | `slide_down` | `slide_left` | `slide_right`), `anim_d` (entrance seconds), `delay` (shift appearance, s, may be negative), `show` (visible for N seconds).
Unset keys inherit from the layout. `false` is meaningful for `shadow_on` / `upper`.

## Layout (`templates/templates.json` -> `templates[]`)
Top level: `id`, `name`, `category`, `mode` (`together|stack|single`), `intro` (s before first element), `fade`, `interval`, `header_delay`, `end_hold`,
`min_hold` (together), `min_duration`, `darken` (0-1 dim over the clip), `header` {style}, `body` {style}, `sample`.

Timing: `together`: all lines appear at `intro + header_delay`, hold = max(`min_hold`, 0.4 s x words). `stack`/`single`: line *i* appears at
`intro + header_delay + i x interval`; video ends `end_hold` after the last line (>= `min_duration`). `single`: each line is replaced by the next.

Style block (`header` / `body`): `font`, `max_size`, `min_size` (auto-fit range px), `color`, `stroke`, `stroke_color`, `align`, `upper`, `line_spacing`, `gap` (px between lines),
`x_margin` (side margin), `y` (top of the text box), `box_h` (box height), `valign` (top|middle|bottom),
`bg` {`mode` line|row, `color`, `opacity`, `radius`, `pad_x`, `pad_y`, `full`}, `shadow` {`color`, `dy`, `blur`, `dx`}, `glow` {`color`, `radius`}.

## Presets (`presets.json`)
`fonts[]`: `{file, label, src}` Instagram style -> font file. `styles[]`: `{id, name, style}` where `style` is a flat override dict (keys above).
Applying a preset to an element first clears `font,color,stroke,stroke_color,upper,bg_*,shadow_*,glow_*`, then sets the preset keys.
Applying to a layout converts the flat keys to the nested `bg/shadow/glow` form.

## `brand.json`
`footer` {enabled, text, style} - persistent bottom text (e.g. `anyhouse.me`). `cta` {enabled, seconds, text, style} - optional end card.

## Safe zones (Instagram Reels, approximate)
Keep important text inside: top 13% (~250 px) and bottom 20% (~380 px) are covered by UI; the right ~11% (~120 px) holds buttons between them.
The footer sits at y = 90% by default - move it if the bottom UI covers it.
