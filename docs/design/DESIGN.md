---
name: The Brutalist Blueprint
colors:
  surface: '#11131c'
  surface-dim: '#11131c'
  surface-bright: '#373943'
  surface-container-lowest: '#0c0e17'
  surface-container-low: '#191b24'
  surface-container: '#1d1f29'
  surface-container-high: '#282933'
  surface-container-highest: '#33343e'
  on-surface: '#e2e1ef'
  on-surface-variant: '#c4c5d9'
  inverse-surface: '#e2e1ef'
  inverse-on-surface: '#2e303a'
  outline: '#8e90a2'
  outline-variant: '#434656'
  surface-tint: '#b8c3ff'
  primary: '#b8c3ff'
  on-primary: '#002388'
  primary-container: '#2e5bff'
  on-primary-container: '#efefff'
  inverse-primary: '#124af0'
  secondary: '#c6c6c7'
  on-secondary: '#2f3131'
  secondary-container: '#454747'
  on-secondary-container: '#b4b5b5'
  tertiary: '#c7c5d0'
  on-tertiary: '#2f3038'
  tertiary-container: '#6d6c76'
  on-tertiary-container: '#f1effa'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dde1ff'
  primary-fixed-dim: '#b8c3ff'
  on-primary-fixed: '#001356'
  on-primary-fixed-variant: '#0035be'
  secondary-fixed: '#e2e2e2'
  secondary-fixed-dim: '#c6c6c7'
  on-secondary-fixed: '#1a1c1c'
  on-secondary-fixed-variant: '#454747'
  tertiary-fixed: '#e3e1ec'
  tertiary-fixed-dim: '#c7c5d0'
  on-tertiary-fixed: '#1a1b23'
  on-tertiary-fixed-variant: '#46464f'
  background: '#11131c'
  on-background: '#e2e1ef'
  surface-variant: '#33343e'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 64px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.4'
spacing:
  unit: 4px
  gutter: 1px
  margin-xs: 16px
  margin-md: 32px
  margin-lg: 48px
  container-max: 1440px
---

## Brand & Style
The design system adopts a **Neo-Brutalist Architectural** aesthetic, emphasizing structure over decoration. It targets a technical, sophisticated audience that values transparency, precision, and high-information density. The UI is designed to feel like a living wireframe—intentional, raw, and unyielding.

The personality is authoritative and structural. By utilizing interlocking blocks and visible container boundaries, the system evokes the feeling of a blueprint or a terminal. High-contrast cobalt blue serves as the sole functional accent against a monochromatic, dark-zinc environment, directing attention through sheer visual weight rather than soft affordances.

## Colors
The palette is strictly functional. The **Deep Black (#09090B)** background provides the foundation, while **Dark Zinc (#18181B)** surfaces define structural blocks. 

- **Primary (Cobalt Blue):** Used exclusively for primary actions, active states, and critical highlights.
- **Surface & Muted:** Mid-zinc is used for the 1px architectural borders that define every UI element.
- **Text:** Off-white provides maximum legibility against the dark surfaces without the jarring vibration of pure white.

## Typography
The typography mirrors the architectural theme. **Space Grotesk** (serving as a substitute for Clash Display's geometric ink-traps) is used for all headlines to provide a technical, high-impact feel. **Hanken Grotesk** provides a clean, neutral balance for body copy.

**JetBrains Mono** is introduced for labels, metadata, and status indicators to reinforce the "blueprint" and "developer-tool" aesthetic. All labels should be uppercase with slightly increased letter spacing for maximum structural clarity.

## Layout & Spacing
The layout is a **Fixed-Grid Modular** system. Unlike traditional fluid layouts that hide their seams, this design system celebrates them.

- **Visible Grids:** Every major section is encased in a 1px #52525B border.
- **Interlocking Blocks:** Components should "snap" together, sharing borders where possible to create a monolithic appearance.
- **Rhythm:** A strict 4px baseline grid ensures vertical alignment.
- **Mobile:** On mobile, the 1px borders remain, but horizontal margins reduce to 16px. Blocks stack vertically, maintaining their 0px radius and rigid structure.

## Elevation & Depth
This design system explicitly rejects shadows and Z-axis depth. Hierarchy is established through **Tonal Layering** and **Line Weight**.

- **No Shadows:** Depth is never communicated via blurs.
- **Tonal Stepping:** The background is the lowest level (#09090B). Interactive surfaces or cards use the Zinc surface (#18181B).
- **Active State:** Focus or active states are indicated by a change in border color to Cobalt Blue or a solid Cobalt Blue fill.
- **Visual Wireframing:** Use 1px internal lines to separate content within a card rather than using background color shifts.

## Shapes
The shape language is strictly **Rectilinear**. There are no rounded corners in the design system. All buttons, inputs, cards, and tags use a 0px border radius. This creates a hard, architectural edge that reinforces the Brutalist Blueprint theme.

## Components

- **Buttons:** Sharp 0px rectangles. Primary buttons are solid Cobalt Blue with Off-White text. Secondary buttons are transparent with a 1px Zinc border. On hover, buttons should invert colors or gain a Cobalt Blue border.
- **Input Fields:** 1px Zinc border with a Deep Black background. Labels are JetBrains Mono, placed strictly above the field or "slotted" into the top border line.
- **Cards:** Defined by 1px #52525B borders. No padding between the card edge and the grid it sits in; it should feel like a cell within a spreadsheet or blueprint.
- **Chips/Badges:** Small rectangular boxes with JetBrains Mono text. Always uppercase.
- **Lists:** Separated by 1px horizontal Zinc lines. No rounded hover states; use a full-width Zinc background fill for hover.
- **Checkboxes/Radio Buttons:** Square 0px boxes. When checked, they fill solid Cobalt Blue. No circular elements are permitted.
- **Progress Bars:** Flat, 0px, Cobalt Blue fill against a Dark Zinc track.