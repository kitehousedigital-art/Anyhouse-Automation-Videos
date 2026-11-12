# Writing and design guide

## Hook (headline)
- <= 9 words, one promise, a number or a tension: "3 signs of a rental scam", "Rent in Utrecht: what you actually pay".
- Specific beats clever. Put the benefit or the surprise first. No clickbait you cannot pay off in the lines.

## Lines
- 3-6 lines. One idea per line. <= 8 words (single) / <= 12 (stack, together). Active voice, concrete nouns.
- Numbered lists: "1. Deposit" style keeps the order obvious; the engine glues "1." to the next word so it never wraps alone.
- Bilingual terms (e.g. Dutch word + English meaning): use a line break - `"1. Borg\nDeposit"`.
- Last line = payoff or soft CTA ("Find homes first - anyhouse.me"). The footer already shows the domain.

## Pacing
- Reading speed on mobile ~ 3 words/second. `interval` 1.8-2.5 s for 5-8 words; 1.2-1.6 s for 2-4 words.
- Total length sweet spot 8-20 s. Hold the last line >= 2 s (`hold`). `describe_video` shows the real timeline.

## Layout choice
| Content | Layout mode |
|---|---|
| list that builds, viewer reads along | `stack` |
| step-by-step, myth/fact, big punchy statements | `single` |
| one headline, one short fact, quote | `together` |

## Style choice (Instagram-style presets)
- Default to **Classic / Modern** + shadow for readability on busy clips.
- **Strong** / **Strong yellow box** for hooks and warnings. **Typewriter box** for "document / receipt" topics (contracts, payslips).
- **Neon** only for 1-3 words (the hook) on dark clips - unreadable for sentences.
- **Elegant / Literature / Signature** for calm, lifestyle tones; avoid for numbers-heavy content.
- Max 2 styles per video (headline + body). Use color only to emphasise: one accent color (#FFD21F AnyHouse yellow) for the key word/line.

## Contrast & fit
- Text over video needs a shadow, outline or box. If the clip is bright, raise layout `darken` (0.2-0.4) or use a box.
- Auto-fit shrinks text; below ~44 px it gets hard to read - cut words.
- Keep clear of the Reels UI zones (see schema.md).

## Fact discipline (rentals / legal / money)
- Rules differ by city and change (deposit caps, rent-increase limits, registration deadlines). State the jurisdiction in the line or caption.
- Cite the primary source (government, municipality, Huurcommissie, tenant union) in `caption`. Add `status:"verify"` if any number is unverified.
- Never present estimates as facts; say "about" / "typically" and name the year.
