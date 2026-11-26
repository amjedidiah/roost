---
name: roost
description: Never miss what your documents say is due. A dark, one-column page that a non-technical person can use on a phone.
colors:
  night: "#111111"
  card: "#1b1b1b"
  raised: "#262626"
  line: "#333333"
  text: "#f4f4f2"
  muted: "#a6a6a6"
  signal: "#ffd60a"
  danger: "#ff8a7a"
  bright: "#ffffff"
typography:
  display:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "clamp(38px, 10vw, 60px)"
    fontWeight: 700
    lineHeight: 1.02
    letterSpacing: "-0.035em"
  section:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
  lede:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.45
  item:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  small:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  micro:
    fontFamily: "Schibsted Grotesk, Helvetica Neue, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "0.06em"
  mono:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "0.3em"
rounded:
  mark: "4px"
  sm: "10px"
  md: "14px"
  lg: "20px"
  full: "999px"
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
    backgroundColor: "{colors.text}"
    textColor: "{colors.night}"
    rounded: "{rounded.sm}"
    padding: "0 24px"
    height: "52px"
  button-primary-disabled:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.muted}"
  pill:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.full}"
    padding: "0 16px"
    height: "44px"
  field:
    backgroundColor: "{colors.night}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "52px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.lg}"
    padding: "24px"
  due-item:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    typography: "{typography.item}"
    rounded: "{rounded.md}"
    padding: "16px"
  date-block:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
  next-line:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.night}"
    rounded: "{rounded.mark}"
---

# Design System: roost

## Overview

**Creative North Star: "The Night Shelf"**

roost is a quiet shelf of your own papers, read at night: one dark column, white type, and a single yellow mark on the next thing you must do. The page is for anyone, not just technical people: every control says what it does in plain words ("Add a document", "Check for changes", "Send me one now", "Delete my account"), and nothing needs explaining.

It refuses three category defaults: the chat thread (roost is a list of dates, not a conversation), the busy dashboard (one column, four sections, no widgets or charts), and the cute bird theme (the roost idea lives only in the name). Dates come from fixed rules over the user's own words, and every item shows the file it came from.

The page is phone first. The same single column, 680px wide at most, serves desktop.

**Key Characteristics:**
- Near-black ground, off-white text, one grey for everything secondary.
- One self-hosted grotesk (Schibsted Grotesk) in two weights.
- Soft-cornered cards on the ground; no borders between cards, no shadows.
- Highlighter yellow on the next upcoming line only.
- Urgency shown by the form of a square mark plus a word, never by colour alone.

## Colors

Restrained: neutrals carry the page; yellow marks one line and a soft red marks lateness and destructive actions.

### Primary
- **Highlighter Yellow** (`signal`, #ffd60a): behind the text of the first upcoming item in Coming up, and behind the to-do in an answer. Also the text caret colour. Never on buttons, links or badges.

### Neutral
- **Night** (`night`, #111111): the page ground; the text colour on the primary button and on the yellow highlight; the inside of input fields.
- **Card** (`card`, #1b1b1b): every card and list row: steps, due items, documents, reminders, account, the ask box.
- **Raised** (`raised`, #262626): surfaces inside a card: the date block, the answer facts, the off state of the switch, the usage bar track, a disabled primary button.
- **Line** (`line`, #333333): 1px borders on fields, pills, the demo note and the drop zone (dashed).
- **Bright** (`bright`, #ffffff): the primary button's hover fill, and nothing else.
- **Text** (`text`, #f4f4f2): primary text, the primary button fill, the switch when on, the usage bar fill, focus outlines.
- **Muted** (`muted`, #a6a6a6): labels, captions, tags, placeholders, secondary text. 7.8:1 on night, 7.1:1 on card and 6.2:1 on raised, so it passes AA at every size used.

### Semantic
- **Danger** (`danger`, #ff8a7a): error notes, the outline of an overdue date block, "Yes, remove" and the delete-account pills. Always paired with words.

### Named Rules
**The One Line Rule.** Yellow marks only the next thing to do: the first upcoming item in Coming up, or the to-do in an answer. A second yellow line on the screen would make both mean less.

**The Words First Rule.** Colour never carries meaning alone: overdue items say "Overdue by N days", urgency has a mark and a word, errors are sentences.

## Typography

**Display Font:** Schibsted Grotesk (with Helvetica Neue, Helvetica, Arial)
**Body Font:** Schibsted Grotesk
**Mono:** ui-monospace stack, for the 6-digit code field only

**Character:** a neo-grotesk set tight and bold at display size and plain at reading size. Self-hosted as one variable woff2 (weights 400–700, SIL OFL 1.1) in `web/assets/`.

### Hierarchy
- **Display** (700, clamp 38–60px, 1.02, -0.035em): the one signed-out headline.
- **Section** (700, 24px, -0.02em): section headings (Coming up, Your documents, Reminders, Ask about your documents, Your account). The lowercase mark in the top bar and the date number in a date block use the same size.
- **Title** (700, 20px): the sign-in card heading and empty-state headings.
- **Lede** (400, 18px, muted): the line under the headline; also the question text in the ask box.
- **Item** (700, 17px, 1.35): the line of a due item. Input fields use 17px at 400.
- **Body** (400, 16px, 1.5): running text and buttons.
- **Small** (400, 15px): notes under forms and the evidence quote in an answer.
- **Label** (400, 14px, muted): tags, usage, captions, the footer, link buttons.
- **Micro** (400, 12px, uppercase, 0.06em): month and weekday in the date block, the only uppercase text.

### Named Rules
**No Tabular Figures.** Figures stay proportional everywhere. In Schibsted Grotesk the `tnum` feature also widens `.` and `,`, which breaks sizes like "1.4 MB".

**The Two Weights Rule.** Only 400 and 700. Emphasis is weight or size, never italics.

## Layout

One centred column, 680px at most, with a 20px side gutter. A 4px-based spacing scale (4, 8, 12, 16, 24, 32, 48, 64) runs the page. Sections are 48px apart; cards in a list are 8px apart.

- **Signed out:** top bar (mark), headline, lede, three numbered steps, the sign-in card, the demo note, footer.
- **Signed in:** top bar (mark, email, Sign out), then Coming up (grouped Overdue / This week / Later), Your documents (usage, drop zone, forward-by-email line, list), Reminders, Ask about your documents, Your account, footer.
- **Phones (480px and down):** form rows stack (field above a full-width button), the date column narrows to 52px.

## Elevation & Depth

Flat. No shadows, blurs or gradients. Depth comes from three steps of ground (night, card, raised) and from space.

### Named Rules
**The Three Grounds Rule.** Night is the page, card is a thing on the page, raised is a part of a thing. Never put a card on a card.

## Shapes

Soft corners on a fixed scale: 20px for big cards, 14px for list rows and steps, 10px for fields, buttons and the date block, full rounding for pills, the switch and the usage bar, 4px for the yellow highlight. Lines are 1px. The only drawn shape is the 11px urgency square, inline SVG in the current text colour.

## Components

### Buttons
- **Primary:** off-white fill, night text, 700, 52px tall, 10px corners ("Email me a code", "Add a document", "Ask"). Hover brightens to pure white, press scales to 98%; disabled turns raised with muted text and shows what is happening ("Sending…", "Signing in…").
- **Pill:** transparent with a 1px line border, full rounding, 44px tall ("Check for changes", "Send me one now", "Sign out"). Danger pills use the danger colour for text and, on hover, the border.
- **Link button:** 14px underlined text with a padded 44px tap area and an equal negative margin ("Remove", "Cancel", "Send a new code").

### Inputs / Fields
- **Field:** night inside a 1px line border, 52px tall, 10px corners; the border turns text-coloured on focus. The code field is mono with wide tracking.
- **Ask box:** a card with a 1px line border and 20px corners holding an auto-growing textarea and the Ask button. Enter asks; Shift+Enter adds a line.
- **Switch:** 52×32 track with a 44px hit area; off is raised with a muted knob, on is text with a night knob. It is a `button` with `role="switch"` and `aria-checked`.

### Due item (signature component)
A card row: a date block (month, day number, weekday) on the left; on the right the exact line from the document in 700, then tags: when it is due ("Due in 6 days", "Overdue by 2 days"), urgency (square mark plus Urgent / Soon / Can wait), the next step (Do it now / Chase it up / Plan it in), and the file it came from. The first upcoming item carries the yellow highlight; an overdue item's date block has a danger outline.

### Urgency mark
An 11px square: filled for Urgent, bottom half filled for Soon, open for Can wait. Always next to the word.

### Inline confirm
Destructive actions never open a dialog. The control is replaced in place by the question and two choices ("Remove? Yes, remove / Cancel", "Yes, delete everything / Cancel"); focus moves to the confirming button, and back to the original control on Cancel.

### Motion
New answers and items rise 10px and fade in (0.5s, `cubic-bezier(.16,1,.3,1)`); the yellow highlight sweeps in once. The usage bar grows with `transform: scaleX`. All of it is off under `prefers-reduced-motion: reduce`.

## Do's and Don'ts

### Do:
- **Do** use plain words a non-technical person would say for every label and button.
- **Do** show the file every date came from.
- **Do** render all document and email text with `textContent`; it is user content.
- **Do** keep touch targets 44px tall.
- **Do** confirm destructive actions inline, and say what will be lost.

### Don't:
- **Don't** add a second yellow line, coloured badges or gradients.
- **Don't** make it a chat: no bubbles, avatars or streamed prose.
- **Don't** draw birds, nests or twigs.
- **Don't** put a card inside a card, or add shadows.
- **Don't** use colour as the only signal for urgency, lateness or errors.
