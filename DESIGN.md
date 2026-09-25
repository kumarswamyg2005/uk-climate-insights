# DESIGN.md — UK Climate Insights

## Subject and job

Public explorer for 100+ years of UK Met Office regional climate records. Primary job: let someone
pick a place and a measure and _see_ how it has changed, then ask questions in plain English.
Vernacular: the climatologist's record book and the warming-stripes chart — long runs of years,
anomalies, colour as temperature.

## The one bold thing

A full-width **climate stripes band** at the top of the explorer: one vertical stripe per year,
coloured by the value's deviation from the series mean (diverging scale). It updates when the selection
changes. Everything else is quiet and disciplined.

## Colour tokens

- `--paper` #F7F8F6 page background (cool, not cream)
- `--ink` #1A2230 text, axes
- `--slate` #5B6676 secondary text, gridlines at 20% opacity
- `--rule` #D9DEE3 borders, dividers
- `--signal` #1F6FB2 the only accent: focus rings, active control, primary action, chart line
- Stripes/diverging scale (for data only, never UI chrome): cold #08306B → #6BAED6 → #F0F0F0 → #FC9272 → #67000D
  For rainfall use a dry→wet scale: #8C510A → #F6E8C3 → #C7EAE5 → #01665E. Sunshine: #3F3F3F → #FEE391 → #EC7014.
  Dark mode: `--paper` #11161E, `--ink` #E6EAF0, `--slate` #9AA5B4, `--rule` #2A3340, `--signal` #5FA8E8.

## Type

- Headings: **Newsreader** (serif, 600) — the record-book voice.
- UI + body + numbers: **Atkinson Hyperlegible** (400/700) — tabular figures on for tables and stats.
- Self-host both (woff2 in static). Scale: 14 / 16 / 20 / 26 / 34 px. Line length ≤ 72ch.
- Sentence case everywhere. No all-caps labels, no eyebrow labels above headings, no mono data labels.

## Layout (explorer, desktop)

```
+--------------------------------------------------------------------------+
| UK Climate Insights                         Explore  Compare  About      |
+--------------------------------------------------------------------------+
| [|||||||||||||||| climate stripes, 1884 → 2026, full width |||||||||||] |
+----------------------+---------------------------------------------------+
| Region   [Scotland v]| Annual rainfall, Scotland, 1884–2025       (mm)   |
| Measure  [Rainfall v]| [ line chart + 10-yr rolling mean toggle      ]   |
| Period   [Annual   v]|                                                   |
| Years    [1884]–[2025]| Wettest 2011  1,968 mm   Driest 1955 …  Trend …  |
| [Download CSV]       | [ table: year | value, sortable, 20 rows + more ] |
+----------------------+---------------------------------------------------+
| Ask about the data  [ Which was the coldest winter in Wales? ] [Ask]     |
|  answer text …                     ▸ Data used (3 rows, get_extreme)     |
+--------------------------------------------------------------------------+
| Data: Met Office UK and regional series (Crown copyright) · updated …    |
+--------------------------------------------------------------------------+
```

Mobile: controls collapse into a top bar that opens a sheet; stripes stay full width; chart then stats
then table then chat. Left-aligned throughout.

## Components

- Controls: native `<select>` styled, visible focus ring in `--signal`.
- Stats: plain rows of label + value, no cards, no shadows.
- Radius: 4px on inputs and buttons only; panels are separated by `--rule` lines, not boxes.
- Chart: Chart.js, no gradient fill, 1.5px line in `--signal`, rolling mean dashed in `--slate`,
  hover tooltip shows year, value, unit.

## Motion

One moment only: stripes cross-fade (200ms) when the selection changes. Respect `prefers-reduced-motion`.

## Copy

Plain, specific. Buttons say what happens: "Download CSV", "Ask", "Compare regions".
Empty: "No values for this range. Widen the years or pick another period."
Error: "Couldn't load the series. Check your connection and try again." Chat unavailable:
"The chat service isn't configured right now. The charts and API still work."

## Forbidden

Gradient hero, identical rounded cards with soft shadows, all-caps eyebrows, arrows appended to buttons,
emoji, cream background with terracotta accent, unstyled component-library defaults, decorative icons.
