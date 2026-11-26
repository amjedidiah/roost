---
name: roost
description: A personal archivist that answers with a typed decision, set as a Swiss data sheet.
colors:
  paper: "#ffffff"
  ink: "#121212"
  graphite: "#6b6b6b"
  hairline: "#d6d6d6"
  wash: "#f3f3f3"
  highlighter: "#ffd60a"
typography:
  display:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "clamp(34px, 9.5vw, 56px)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  value:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 400
    lineHeight: 1.3
  body:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  none: "0px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
  s8: "64px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.none}"
    padding: "0 24px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
  button-primary-disabled:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.graphite}"
  input-question:
    textColor: "{colors.ink}"
    typography: "{typography.value}"
    rounded: "{rounded.none}"
    padding: "8px 0 12px"
  input-token:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.mono}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "44px"
  action-line:
    backgroundColor: "{colors.highlighter}"
    textColor: "{colors.ink}"
    typography: "{typography.title}"
  code-panel:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink}"
    typography: "{typography.mono}"
    padding: "16px"
---

# Design System: roost

## Overview

**Creative North Star: "The Data Sheet"**

Every answer roost gives is set as a numbered data sheet in the International Typographic Style: typed fields on a strict grid, ruled in ink, with the one line that matters marked as if by highlighter. The page refuses the two category defaults: the chat thread, because roost returns fields, not conversation, and the rounded-card dashboard, because the content is a single decision, not a wall of widgets. The roost metaphor stays in the name and the copy ("the nest"); it is never drawn.

The system is quiet by default and dense where it counts. White paper, black ink, one grey for everything secondary, and a single signal colour that appears on exactly one line per answer. Hierarchy comes from weight, size and rule weight, never from colour or containers. It reads as a well-set form: labels small and grey, values large and black, every row separated by a hairline, every group closed by an ink rule.

The world is phone-first: one column of stacked label-over-value rows on a phone, and a two-column page (question left, sheet right) from 1040px.

**Key Characteristics:**
- White sheet, black ink, square corners everywhere.
- One self-hosted grotesk (Schibsted Grotesk) in two weights.
- Numbered field rows separated by hairlines and closed by ink rules.
- Highlighter yellow behind the action line, and nowhere else.
- Priority shown by the form of a square mark, not by colour.

## Colors

Restrained: neutrals carry the page, and one signal colour marks the single most important line.

### Primary
- **Highlighter Yellow** (`highlighter`): sits behind the action line on the decision sheet, the to-do quoted from the user's own document. It never appears on buttons, links, badges or focus states.

### Neutral
- **Sheet White** (`paper`): the page ground and the inverse text on the primary button.
- **Press Ink** (`ink`): all primary text, the 1px and 2px structural rules, the primary button fill, focus outlines, and the priority marks.
- **Graphite** (`graphite`): field labels, captions, secondary values (relative dates, scores below the winner), placeholders, and disabled text. It passes AA on white for text at 14px and up.
- **Hairline Grey** (`hairline`): the 1px dividers between rows inside a group, and the placeholder dashes of an empty sheet.
- **Wash** (`wash`): the background of the raw JSON panel only.

### Named Rules
**The One Line Rule.** Highlighter yellow marks exactly one line per answer: the action quoted from the source file. Any second use of yellow dilutes the one claim the page exists to make.

**The Ink Hierarchy Rule.** Hairline grey separates rows inside a group; ink closes a group (2px under a sheet head, 1px above the first row and below the action). Never use ink between ordinary rows.

## Typography

**Display Font:** Schibsted Grotesk (with Helvetica Neue, Helvetica, Arial)
**Body Font:** Schibsted Grotesk
**Label/Mono Font:** ui-monospace stack, only for the token field and raw JSON

**Character:** A neo-grotesk in the Swiss lineage, set tight and black at display size and plain at reading size. It is self-hosted as one variable woff2 (weights 400–700, SIL OFL 1.1) in `web/assets/`.

### Hierarchy
- **Display** (700, clamp 34–56px, 1.02, -0.035em): the one page heading ("Ask your documents.").
- **Headline** (700, 22px, 1.2): the sheet head ("Decision", "Not in the nest").
- **Title** (700, 21px, rising to 24px at 720px and up): the action line on the sheet.
- **Value** (400, 19px, rising to 21px at 720px and up): field values on the sheet. The question field uses the same voice at 20px (26px at 1040px and up).
- **Body** (400, 16px, 1.45): running text. The lede is 17px (16px on phones). Passages are capped at 62ch.
- **Label** (400, 14px, graphite): field labels, captions, the nest line, and secondary metadata. Sentence case, no tracking, never uppercase.

### Named Rules
**The Dates-Only Tabular Rule.** Tabular figures apply to dates only. In Schibsted Grotesk the `tnum` feature also widens `.` and `,`, so scores and prose stay proportional ("0.49", not "0 . 49").

**The Two Weights Rule.** Only 400 and 700. Emphasis is weight or size, never italics, colour or tracking.

## Layout

A single 4px-based spacing scale (4, 8, 12, 16, 24, 32, 48, 64) runs the whole page. The gutter is 20px on phones and 40px from 720px.

- **Phone (under 560px):** one column in the order question, decision sheet, sample questions. Sheet rows stack the label above the value, with any aside (relative date) on the label's line. Blank rows keep the dash on the label's line, so all six fields of an empty sheet fit the first screen.
- **720px and up:** sheet rows become a three-column grid: a 9em label column, the value, and a right-aligned aside.
- **1040px and up:** a 5:7 two-column page. The question and the sample questions sit on the left, and the decision sheet spans the right.

The masthead is a single ruled band: the lowercase mark on the left, the nest count and Re-ingest on the right. More space sits above a group's rule than below it.

## Elevation & Depth

Completely flat. There are no shadows, blurs or layered surfaces. Depth and grouping come only from rule weight (hairline vs. ink) and from whitespace. The one tonal surface is the wash behind the raw JSON panel.

### Named Rules
**The Paper Rule.** Nothing floats. If an element needs separating, give it a rule or space, never a shadow or a card.

## Shapes

Square everywhere (0px radius): buttons, inputs, the token field and the JSON panel. Lines are 1px, with 2px reserved for a sheet head and the question field's underline (4px when focused). The only drawn shapes are the 12px priority squares and the 18px arrow on sample rows, both authored inline SVG in ink.

## Components

### Buttons
Blunt and printed: a solid ink block with white bold type.
- **Shape:** square (0px), 48px tall, 24px side padding.
- **Primary:** ink fill, white 700 label ("Ask", "Save").
- **Hover / Focus:** inverts to white with ink text and an ink border over 0.2s. Focus is a 2px ink outline offset 3px.
- **Disabled:** white with graphite text and a hairline border ("Asking…").
- **Text buttons:** "Re-ingest" and "Change" are 14px ink text with a 1px underline offset 3px, thickening to 2px on hover. Their tap area is padded to 44px with an equal negative margin, so the layout does not move.

### Inputs / Fields
- **Question field:** an auto-growing textarea with no box, only a 2px ink underline that thickens to 4px on focus. Enter asks; Shift+Enter adds a new line. The placeholder is graphite.
- **Token field:** a 1px ink box, 44px tall, set in mono, beside a primary Save button.
- **Error:** the notice line under the question field, in ink, with a bold lead ("Couldn't ask.") followed by what to do next.

### Navigation
The masthead is the only navigation: the mark links home, the nest count opens a two-column list of documents and passage counts, and Re-ingest reports the sync result in that same panel.

### Decision Sheet (signature component)
A numbered form. The head carries the title and "match 0.49", followed by the quoted question. Then six rows: 1 Source (700), 2 Category, 3 Priority (square mark plus word), 4 Next action, 5 Due (date with a right-aligned "in N days"), 6 Action (the highlighted to-do, captioned "Quoted from the “To do” list in <file>"). Below the rows come the best-matching passage (heading in 700, a 1px ink rule on the left), the ranked passages (the winner in ink, the rest in graphite), the summary line, and a Raw JSON disclosure. An empty sheet shows the same labels with hairline dashes. A not-answered sheet says "Not in the nest" and explains the 0.28 threshold.

### Priority Mark
A 12px square in ink: filled for high, bottom half filled for medium, open outline for low. Always shown with the word.

### Motion
One authored moment. When an answer arrives, each part of the sheet is revealed left to right with `clip-path` in order (70ms apart, 0.5s, ease-out `cubic-bezier(.16,1,.3,1)`), then the highlighter sweeps across the action line. Nothing animates with `prefers-reduced-motion: reduce`.

## Do's and Don'ts

### Do:
- **Do** keep yellow behind the action line only (The One Line Rule).
- **Do** show priority by mark form plus the word, never by colour alone.
- **Do** say where every value came from: the file name on the sheet, and a caption naming the list the action was quoted from.
- **Do** render all document text with `textContent`; it is user content.
- **Do** keep every corner square and every rule 1px (2px for a head, 4px for focus on the question field).

### Don't:
- **Don't** add rounded cards, shadows, colour-to-colour gradients or coloured badges; the sheet is flat paper. (The highlighter is a single-colour `linear-gradient` only so its width can animate.)
- **Don't** make it a chat: no bubbles, avatars or streamed prose.
- **Don't** draw birds, nests or twigs; the roost idea lives in the name and the copy.
- **Don't** number lists whose order means nothing (the sample questions stay unnumbered); the sheet's field numbers stay.
- **Don't** turn on tabular figures for scores or prose in Schibsted Grotesk (The Dates-Only Tabular Rule).
