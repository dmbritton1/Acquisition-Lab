---
name: Acquisition Lab analyst board
description: A graphite-dark workspace for private-equity analysts pricing a deal.
colors:
  bg: "#0e1014"
  panel: "#15181e"
  raise: "#1c2028"
  sunk: "#0b0d10"
  ink: "#e6e8eb"
  muted: "#9aa1ab"
  faint: "#737a85"
  line: "#262b34"
  line-2: "#333a45"
  track: "#2a303a"
  accent: "#8ab4ff"
  accent-fill: "#3b63d9"
  accent-soft: "#1a2540"
  go: "#47cd89"
  go-soft: "#0f2a1d"
  bad: "#f97066"
  bad-soft: "#2c1515"
  warn: "#fdb022"
  warn-soft: "#2e2410"
  bar-ok: "#3b7d5a"
  bar-bad: "#8a3a34"
typography:
  family: "-apple-system, BlinkMacSystemFont, Segoe UI, system-ui, Roboto, sans-serif"
  brand: { fontSize: "15px", fontWeight: 600 }
  verdict: { fontSize: "22px", fontWeight: 600 }
  figure: { fontSize: "22px", fontWeight: 600, letterSpacing: "-0.01em" }
  heading: { fontSize: "13px", fontWeight: 600 }
  body: { fontSize: "14px", fontWeight: 400, lineHeight: 1.45 }
  small: { fontSize: "12px", fontWeight: 400 }
  tag: { fontSize: "11px", fontWeight: 400 }
rounded:
  control: "6px"
  card: "8px"
  dialog: "10px"
  tag: "4px"
spacing:
  gap: "12px"
  card: "16px"
components:
  button-primary: { backgroundColor: "{colors.accent-fill}", textColor: "#ffffff", rounded: "{rounded.control}" }
  button: { backgroundColor: "{colors.raise}", border: "{colors.line-2}", rounded: "{rounded.control}" }
  input: { backgroundColor: "{colors.sunk}", border: "{colors.line-2}", textColor: "{colors.ink}", rounded: "{rounded.control}" }
  verdict-nogo: { backgroundColor: "{colors.bad-soft}", textColor: "{colors.bad}" }
  verdict-go: { backgroundColor: "{colors.go-soft}", textColor: "{colors.go}" }
---

## Overview

A quiet, dark workspace for analysts deciding what to pay, in the spirit of Linear or Vercel: graphite surfaces, grey
text, one blue accent. It replaced a black-and-amber Bloomberg-style terminal on 2026-11-12, because the terminal
props (amber everywhere, numbered hotkey bar, `>` prompt) read as costume rather than an enterprise tool.

## Colors

- Three greys carry the structure: `bg` for the page, `panel` for cards, `raise` for buttons and tags. `sunk` is for
  inputs and raw document text.
- Text is `ink` for figures and titles, `muted` for labels and help, `faint` for hints.
- Blue is the only accent: the primary button, links, slider fills, the asking price and anything the analyst set.
- Red and green are deal signals only (green good, red bad), shown as a soft tint with coloured text, never as a
  solid block. The chart's bars use the dimmer `bar-ok` and `bar-bad`.

## Typography

The system UI font (SF Pro on a Mac, Segoe UI on Windows), so the page loads nothing from outside. Numbers use
tabular figures. SF Mono only for raw document text and shell commands. Headings are small and white, not coloured.

## Layout

A sticky header (brand, deal picker, New deal), then quiet section links whose numbers are working keyboard
shortcuts. Below that, a main column beside a 400px side column on a 12px gap; the side column drops under the main
one below 1180px. Below 640px the deal picker takes its own row and the verdict sits above the three figures.

## Elevation & Depth

Mostly flat: cards are separated by 1px `line` borders. Shadows only on floating things: the open deal picker, the
new-deal dialog and the document panel.

## Shapes

Soft corners: 4px tags, 6px controls, 8px cards, 10px dialog. Slider thumbs are round.

## Do's and Don'ts

- Do keep one accent colour. If something needs attention, use weight or position before colour.
- Do keep red and green for deal signals.
- Do keep the page self-contained, with no outside requests.
- Don't bring back solid coloured blocks, coloured headings, glows or gradients.
