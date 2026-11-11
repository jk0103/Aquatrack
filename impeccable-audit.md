# Aquatrack UI audit (Impeccable 4.7)

Run on 21 Oct 2026 against the `claude/ui-design` branch: Impeccable's detector over `frontend/app`, a rendered scan of the login page, and checks in the browser on the logged-in pages (light mode, laptop width). Nothing has been changed yet.

## Score: 14/20 (Good)

| # | Area | Score | Main finding |
|---|------|-------|--------------|
| 1 | Accessibility | 3/4 | Light grey text is too faint to read comfortably in about 12 places |
| 2 | Performance | 2/4 | Three big blurred, moving colour blobs sit behind every page, plus blur on every card |
| 3 | Theming | 3/4 | Dark mode works, but about 40 colours inside the gauges and charts are fixed and don't switch |
| 4 | Responsive | 3/4 | Layouts adapt well; several buttons are smaller than a comfortable tap size (44 px) |
| 5 | Design integrity | 3/4 | Two "AI-looking" patterns flagged; sample numbers look like real results |

## Findings

**[P1] Faint grey text fails contrast.** `text-slate-400` (#94a3b8 on white, about 2.6:1, needs 4.5:1) is used for "Rest" in the week strip, the "/12" in the training gauges, chart axis labels, input placeholders and a few captions. The tagline on the login page's blue panel is 4.0:1. Fix: use the next darker grey.

**[P1] Small tap targets.** Light/dark switch buttons 36×32, the round ↗ card buttons 36×36, the video buttons 36×36, "Log out" 41×16, and the All/Focus/Watch/Good chips are about 32 px tall. Fix: give each a 44 px tap area without changing how it looks.

**[P2] Heavy background effects.** `WaterBackdrop` (AppShell) animates three 400–480 px `blur-3xl` blobs on every page, and every card and the sidebar use `backdrop-filter: blur`. That is smooth on a laptop but can stutter and drain battery on phones. Fix: keep the blobs still (or drop to one), and lower the card blur.

**[P2] Sample numbers look real.** "+4 this month", "−3.5 s since May", "2 of 5 sessions", the training plans and the example feedback show as if they're the user's own results. Fix: mark them as examples until real data exists.

**[P2] Thick coloured left border.** Calendar day events use `border-l-4`, which the detector flags as the most common AI-generated UI tell (`calendar/page.tsx:188`). Fix: a small coloured dot or a soft tinted background instead.

**[P3] Bouncy easing.** The count badge on the filter chips uses an overshoot curve (`FeedbackStage.tsx:674`). Fix: a smooth ease-out like everything else.

**[P3] Fixed colours in gauges and charts.** Needle, ticks, chart line and dots use hex values, so they don't adapt to dark mode. Fix: switch them to the theme colours.

**[P3] Login heading wraps unevenly.** "See your stroke. Swim faster." leaves one short word on the second line. Fix: balanced text wrapping.

## What's working well

- Every link and button shows a visible focus ring when using the keyboard.
- All animations respect the "reduce motion" setting.
- Form fields have labels, and errors are announced.
- The hero photo is optimised and stored in the project.
- Dark mode covers every page from one place (`globals.css`).

## Suggested order

1. Contrast and tap targets (P1)
2. Lighter background effects and labelling sample data (P2)
3. Calendar border, easing, theme colours, heading wrap (P2–P3)
