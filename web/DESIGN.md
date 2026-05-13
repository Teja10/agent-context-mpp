# Thoth — Neo-Academic Design Language

A warm, literary aesthetic inspired by academic journals and review publications. Conveys trust, intellectual weight, and distinction without the typical web3 look.

## Color Palette

| Token | Hex | CSS Variable | Usage |
|-------|-----|-------------|-------|
| Ivory | `#fafaf8` | `--ivory` | Page backgrounds |
| Parchment | `#fdfcf9` | `--parchment` | Card/input backgrounds |
| Sand | `#f5f0e8` | `--sand` | Subtle section backgrounds, editor chrome |
| Tan | `#f0e8d8` | `--tan` | Tag pills, toolbar buttons, hover states |
| Khaki | `#e8dcc8` | `--khaki` | Borders, dividers, tab underlines |
| Camel | `#d4c5a9` | `--camel` | Input borders, muted UI elements |
| Brass | `#c9a962` | `--brass` | Primary accent — active tabs, blockquote borders, gold dividers, publish button |
| Stone | `#a89880` | `--stone` | Muted text, placeholders, timestamps |
| Umber | `#8b7355` | `--umber` | Secondary text, labels, nav links |
| Walnut | `#6b5d4f` | `--walnut` | Secondary body text, summaries |
| Espresso | `#2c2416` | `--espresso` | Primary text, dark backgrounds (editor nav, buttons) |

### Status Colors

| State | Background | Text |
|-------|-----------|------|
| Published | `#e8f5e8` | `#3a7a3a` |
| Draft | `--tan` | `--umber` |
| Purchased | `#e8f5e8` | `#3a7a3a` |

## Typography

| Element | Font | Size | Weight | Style | Spacing |
|---------|------|------|--------|-------|---------|
| Page titles | Georgia, serif | 28px | 400 | italic | — |
| Article headings (h1) | Georgia, serif | 22px | 400 | italic | — |
| Article headings (h2) | Georgia, serif | 18px | 400 | italic | — |
| Brand / nav logo | Georgia, serif | 16-18px | 400 | normal | letter-spacing: 1px |
| Uppercase labels | system-ui, sans-serif | 9-10px | 500 | uppercase | letter-spacing: 1-2px |
| Body text | system-ui, sans-serif | 14px | 400 | normal | line-height: 1.8 |
| Metadata / secondary | system-ui, sans-serif | 12-13px | 400 | normal | — |
| Small annotations | system-ui, sans-serif | 10-11px | 400 | normal | — |

### Key Principle

Headings are always **Georgia italic at normal weight** — never bold. This is the signature of the Neo-Academic style. Bold Georgia looks heavy and generic; italic Georgia feels editorial and refined.

## Components

### Buttons

- **Primary**: `--espresso` background, `--ivory` text, 3px border-radius, 12px font
- **Accent (Publish)**: `--brass` background, `--espresso` text, 3px border-radius
- **Outline**: transparent background, 1px `--umber` border, `--camel` text
- **No rounded pill shapes** — use 3px border-radius for subtle rounding

### Tags / Pills

- Background: `--tan`
- Text: `--umber`
- Border-radius: 10px (pill shape — exception to the 3px rule)
- Font: 10px
- Removable tags add an "x" with `opacity: 0.6`

### Cards

- Background: `--parchment`
- Border: 1px solid `--khaki`
- Border-radius: 6px
- No shadow by default
- **Login card exception**: stacked box-shadows for raised effect: `0 1px 0 #c9b896, 0 2px 0 #c9b896, 0 4px 0 rgba(139, 115, 85, 0.15), 0 8px 24px rgba(44, 36, 22, 0.12), 0 16px 48px rgba(44, 36, 22, 0.08)`

### Inputs

- Background: white
- Border: 1px solid `--camel`
- Border-radius: 4px
- Padding: 7-8px 10-12px
- Focus: border color shifts to `--brass`

### Blockquotes

- Left border: 3px solid `--brass`
- Padding-left: 16px
- Text: italic, `--walnut` color
- Used in article body and summary callouts

### Status Badges

- Small uppercase text (9px), letter-spacing: 0.5px
- Padding: 2px 8px, border-radius: 3px
- Published/Purchased: green bg/text
- Draft: `--tan` bg, `--umber` text

### Dividers

- Decorative: 2px height, `--brass` color, 40px wide, centered
- Used below article titles and in the login card header
- Section borders: 1px solid `--khaki`, full width

## Layout

### Max Widths

- Home feed: 720px centered
- Article reading: 560px centered
- Editor content: 640px centered
- Login card: 370px

### Page Backgrounds

- Default: `--ivory` (`#fafaf8`)
- Login: warm gradient `linear-gradient(160deg, #f5f0e8, #e8dcc8, #d4c5a9)` with subtle diagonal hatching overlay at 3% opacity
- Editor: `--sand` background with `--ivory` content area

### Navigation

- **Default nav**: `--ivory` background, 1px `--khaki` bottom border, "THOTH" brand in Georgia serif left, wallet button right
- **Editor nav**: `--espresso` background, `--camel` text, "THOTH / Editor" with Save Draft (outline) and Publish (brass) buttons right

## Page-Specific Notes

### Home Feed

- Hero section centered with italic Georgia tagline
- "LATEST ARTICLES" section label: uppercase, `--umber`, letter-spacing: 2px, `--khaki` bottom border
- Article cards: no border/shadow, separated by 1px `--tan` bottom border
- Price shown right-aligned: primary number + small "PATHUSD" label below

### Article Reading Page

- "THOTH REVIEW" uppercase label above title
- Title → brass divider → author/date → summary callout (gold-accented) → tags → paywall or body
- Paywall card: centered, gradient background `linear-gradient(180deg, --parchment, --sand)`, 1px `--khaki` border
- Purchased state: green "Purchased" badge inline before body

### Editor

- Title field is inline — large italic serif, not in a form
- Slug auto-generates below title in `--stone` color
- Three-tab bar centered: Write / Agent Context / Settings
- Active tab: `--espresso` text, 2px `--brass` bottom border
- Inactive tab: `--umber` text, no border
- Write tab has optional toggle for slim agent context preview panel
- Agent context tab: full-width editing of key claims (numbered cards), allowed excerpts (brass left-bordered), citation (monospace), license
- Publish readiness shown as pill badges (green = set, brass = partial)

### Login

- Card positioned in **upper-third** of page (not vertically centered)
- Raised card effect with stacked shadows, **no gold top border**
- "WELCOME TO" small uppercase label, then italic "Thoth", then brass divider
- Wallet options, "or" divider, email input, Google button
- "Powered by Privy" footer text
