# Design direction: frontend

The visual identity for the tracker's UI. This is the reference for any frontend work. It is opinionated on purpose. When building a component, match this; do not introduce new colors, effects, or shapes that aren't described here.

## The feeling in one line

A sleek command center for my application pipeline: dense and data forward like a control panel, mostly near-black and high contrast, with purple appearing rarely, like concentrated energy or light seeping through the dark. Premium through restraint, not decoration. Purple is an accent that should feel like it costs something to use, never a color wash.

## The core rule: drama in the frame, calm in the data

This is the most important principle and it resolves the central tension. The theme is heavy, but the heaviness lives in the chrome around the content: backgrounds, borders, headers, empty states, nav, panel edges. The actual data (the applications table, form fields, detail values) stays clean, high contrast, and easy to scan. The styling surrounds the information; it never competes with it. A dense tracker has to be readable first. If a decorative choice makes the pipeline harder to read at a glance, it loses.

## Theme character

Abstract advanced-civilization geometry, not literal. The mood is "ancient and advanced at once," rendered as my own abstract design language. Explicitly avoid: the words or logos of any franchise, and any specific real-world culture's iconography or motifs. This is an original abstract geometric-organic style, not a reference to any real tradition. Keep it clearly my own design so it reads as intentional and professional on a portfolio a recruiter will see.

## Color

Purple only, and used rarely. No gold, no second accent color. Black clearly dominates; purple is a rare accent.

- Base background: near true black with a very subtle purple undertone (around #0A0810 to #100C16). Black is the dominant color, not purple.
- Surfaces (cards, panels, table container): a small step up from the base, still very dark. Distinguished from the base by subtle lightness and borders, not by purple.
- Purple accent (around #8B5CF6): appears only on a short list of things, and nowhere else:
  - the primary action (New Application button)
  - the currently selected/active row
  - focused inputs and links
  - one genuinely important "win" state in the data (an offer), so purple actually signals something when it appears
- Everything else, most status badges, priority indicators, most borders, secondary text, uses greys and near-white, not purple. If purple is showing up in more than a few places on a screen, it is overused; pull it back.
- Text: near-white for headings, soft light grey for body, dimmer grey for secondary/muted labels. High contrast for a dense layout.

## Background patterns

- Style: abstract geometric-organic. Flowing, textured, patterned, but constructed from geometry rather than literal imagery.
- Presence: subtle and low-opacity. Texture you feel more than see. It should never fight the data for attention. Think faint etched material, not wallpaper.
- Placement: backgrounds of the app shell, headers, empty states, and large negative-space areas. Not behind dense data.

## Shape language

Mixed, on purpose, because organic patterns and command-center structure want different things:

- Structural frames (cards, panels, the table container, nav): crisp, minimal rounding. These read as the control-panel skeleton.
- Interactive elements (buttons, inputs, status badges, tabs): a touch softer/rounded so they feel tappable and echo the organic curves.

## Effects

- Subtle purple glow on interactive elements in their active, focused, and hover states (focused input, active/selected row, hovered button). Subtle is the operative word: a soft violet emphasis, not a neon bloom.
- Otherwise keep surfaces matte and flat. The glow is a focus signal, not ambient decoration.

## What to avoid

- Gold or any non-purple accent.
- Literal franchise references or real-world cultural motifs.
- Heavy styling on the data itself (busy table rows, patterned backgrounds behind text, over-decorated cells).
- Neon, high-bloom glows, or gradients strong enough to notice as gradients.
- Anything that trades readability for drama in the dense views.

## Consistency note

Each of my projects has its own color identity (M.I.L.E.S./Nova is electric blue, the portfolio root is green). This tracker is the purple one. The through-line across projects is typography, spacing, and quality bar, not color. Keep this identity specific to the tracker.