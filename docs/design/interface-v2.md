# Interface v2 — Graphite & Iris, in motion

The second iteration of the OpsPilot interface. It keeps the Graphite & Iris
palette and the accessibility guarantees of the first version and adds depth,
motion, and a keyboard-first shell, so the command center feels as precise as
the tools on-call engineers already live in (Linear, Vercel, Raycast).

Inspiration: [Motion Primitives](https://motion-primitives.com) and
[Watermelon UI](https://ui.watermelon.sh), both MIT licensed. OpsPilot ships its
own implementations in `apps/web/src/components/motion/`; files closely
adapted from either project say so in a header comment and keep the MIT notice.

## Principles

1. **Calm by default, alive when it matters.** A healthy system is still: no
   looping animation runs while every service is healthy and nothing is being
   investigated. Motion appears where state changes — a counter moving, a new
   timeline entry, an unhealthy node, an agent at work.
2. **Motion explains, never decorates.** Every animation answers "what changed"
   or "where did it go": a highlight slides to the selected tab, a row expands
   into its detail view, a number counts to its new value.
3. **Nothing depends on motion or 3D.** Every action works with
   `prefers-reduced-motion: reduce`, without WebGL, and from the keyboard.
   Motion components collapse to instant state changes; the 3D topology always
   has the 2D map and the details panel beside it.
4. **Colour is information.** About 90% of every screen is graphite. Iris marks
   OpsPilot itself (primary actions, focus, selection, agent activity); status
   colours mark status only and always travel with an icon and a label.
5. **Keyboard first.** `⌘K` / `Ctrl K` opens the command palette from anywhere;
   every interactive element has a visible Iris focus ring.
6. **Fast first paint.** Motion code is never on the LCP path: headings and
   primary content render as plain HTML, enhancements hydrate after. The 3D
   topology and the command palette load lazily.

## Tokens

All colours live once in `apps/web/src/app/globals.css` and are mirrored in the
Tailwind theme (`@theme inline`) and read by the R3F scene at runtime.
Components never use raw hex. `apps/web/src/app/tokens.test.ts` checks every
text and status token against every surface for WCAG AA (4.5:1).

| Group | Tokens | Notes |
|---|---|---|
| Surfaces | `--background`, `--surface-1..3`, `--surface-glass` | Elevation by tone, unchanged from v1 |
| Depth | `--surface-sheen`, `--edge-highlight`, `--shadow-1..3` | Sheen is a 3% white top gradient; edge highlight is a 1px inset top line, so panels read as lit from above |
| Text | `--text-primary`, `--text-secondary`, `--text-muted` | AA on every surface |
| Iris | `--accent`, `--accent-hover`, `--accent-subtle`, `--accent-glow`, `--on-accent` | Glow is for focus/selection/agent activity only |
| Status | `--status-healthy/degraded/critical/unknown` and `-subtle` fills | Subtle fills are badge backgrounds; the label text uses the full colour |
| Charts | `--chart-neutral-1..3` | Neutrals plus at most one status colour |
| Texture | `--noise` | A 2% SVG noise tile on the backdrop to stop gradient banding |
| Shape | `--radius-sm` 8, `--radius-card` 14, `--radius-lg` 20 | |
| Spacing | Tailwind 4px scale | Page gutters 16/24/32, card padding 20, row height 44 |

Typography: Geist (UI) and Geist Mono (ids, metrics, timestamps), self-hosted
through `next/font`. Metrics use `tabular-nums` so animated digits do not
jitter. Scale: 12 / 13 / 14 / 16 / 20 / 28 / 36, tracking tightened above 20.

## Motion language

Built on the `motion` package. The root `MotionConfig reducedMotion="user"`
turns transform and layout animations off for users who ask; components that
animate other properties (numbers, text, canvas) check `useReducedMotion()`
themselves and render the final state.

| Token | Value | Use |
|---|---|---|
| `--duration-instant` | 100 ms | Hover colour, press feedback |
| `--duration-fast` | 150 ms | Exits, tooltips, toasts out |
| `--duration-base` | 220 ms | Enters, panel cross-fades |
| `--duration-slow` | 320 ms | Drawers, dialogs, shared-element moves |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Everything entering |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | Things moving across the screen |
| `spring.snappy` | stiffness 520, damping 42 | Highlights, toggles, nav indicator |
| `spring.smooth` | stiffness 320, damping 34 | Layout and shared-element transitions |
| `spring.gentle` | stiffness 170, damping 26 | Animated numbers, tilt |

Rules:

- Enter = fade from 0 and rise 4–8 px, `--duration-base`, ease-out. Exit is
  faster than enter.
- Lists stagger by 30 ms, capped at 8 items, so long lists never feel slow.
- Live entries (alerts, timeline events) slide in from the top with a brief
  Iris edge that fades; they never reorder existing rows under the pointer.
- Numbers spring to their new value; digits slide (Sliding Number) when the
  value is a count that people watch, such as open incidents.
- Severity pulse: a soft ring on critical items only, while they are active.
- Agent activity: an Iris Border Trail around the investigation panel while an
  investigation runs; Text Shimmer on its status line.
- Nothing loops in an idle, healthy state.

## Component inventory

**Motion primitives** (`components/motion/`): `MotionProvider`,
`AnimatedBackground` (sliding highlight), `AnimatedNumber`, `SlidingNumber`,
`TextShimmer`, `BorderTrail`, `Spotlight`, `GlowEffect`, `InView`,
`TransitionPanel`, `Tilt`, `ProgressiveBlur`.

**UI primitives** (`components/ui/`): `Button`, `Card`, `Input`, `Textarea`,
`Select`, `Field` (label, hint, error wiring), `Checkbox`, `Table` (sortable
columns, sticky header, row links), `Tabs` (sliding indicator), `Drawer`,
`Modal`, `Toast` (springs in, swipe/close out), `Skeleton` (shimmer),
`EmptyState`, `Badge`, `Kbd`.

**Shell**: sidebar with an animated active highlight, top bar with breadcrumbs
and a search button, `⌘K` command palette (navigation, recent incidents,
services, actions), mobile drawer.

**Pages**: command center (animated KPIs, live alert stream, severity chart,
topology), incidents list (shared Table, any-assignee filter) and detail
(shared-element title, streaming timeline, investigation panel), services and
topology (glow on unhealthy nodes, flow particles on failing edges, camera
fly-to on selection), runbooks, ML detector, audit log, system status, login.

## Topology

- Nodes keep their status shapes (sphere, cone, box, octahedron) so colour is
  never the only signal.
- Unhealthy nodes get an additive halo sprite (bloom-like, no post-processing
  pass); healthy nodes stay matte.
- Flow particles travel along failing edges and along the selected service's
  edges only — never across the whole graph.
- Selecting a service (in 3D, 2D, the list, or the palette) flies the camera to
  it with a damped ease; reduced motion jumps instantly.
- Rendering pauses off-screen and in hidden tabs; quality drops on slow devices.

## Accessibility and performance gates

- WCAG AA for every text/status token on every surface (unit test).
- Visible focus everywhere; palette, dialogs, and drawers trap and restore focus.
- Layouts verified at 1440, 1024, 768, and 390 px (Playwright).
- Visual regression snapshots for the main pages (`toHaveScreenshot`, animations
  disabled, live timestamps masked) run in CI with the e2e suite.
- Lighthouse performance ≥ 85 and accessibility ≥ 90 on primary pages
  (`make test-lighthouse`).
