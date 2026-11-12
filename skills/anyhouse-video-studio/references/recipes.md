# Recipes

## A. "Make 5 videos about X"
`list_videos` (avoid duplicates) -> research -> `upsert_video` x5 (mix layouts) -> `style_element` presets -> `describe_video` + `preview_frame` each -> fix -> `render_videos(ids, quality="draft")` -> report table + sources.

## B. Restyle a whole batch consistently
`set_layout_style(layout_id, "header", "strong")` and `("body", "classic")` changes every video on that layout. Per-video accents stay in `style_element`. Re-preview 2-3 videos.

## C. Fix "text too small / overlapping"
`describe_video` -> find elements with low `font_px` or overlapping boxes -> shorten lines (preferred) -> or `style_element(..., style={"size": 64})` -> or switch layout (`update_video(id, {"template": "single_big_center"})`) -> preview.

## D. Cover image for a finished video
`describe_video` -> pick `t` when the headline + key line are visible -> `export_cover(id, t)`. For design-tool polish use `include_text=False`.

## E. Sheet -> videos -> render
`import_sheet(url, dry_run=true)` -> check mapping -> `import_sheet(url, dry_run=false, layout="list_cards_stack")` -> `style_element(id, "all", preset="modern")` for each (or `set_layout_style`) -> preview -> render.

## F. A/B hooks
`duplicate_video(id, new_id)` -> `update_video(new_id, {"header": "..."})` -> render both in draft.

## G. New layout
`get_layout(existing)` -> copy, change `id/name`, tweak `y`, `max_size`, `bg`, etc. -> `upsert_layout(new)` -> `update_video(id, {"template": new})` -> preview. Use fractions, not px, for positions.

## H. Localised variants
`duplicate_video` -> translate `header`/`lines`/`caption` -> keep structure identical (line count and rough length) so timing stays the same -> choose a font with the needed glyphs (Poppins/Inter/Gabarito cover Latin; check special characters in the preview).

## I. Things the engine cannot do yet (say so; see docs/ROADMAP.md)
Emoji/flags (stripped), voice-over/TTS, music mixing, auto-captions from audio, multi-clip cuts inside one video, exporting an editor timeline (CapCut/Premiere/DaVinci), posting to platforms.
