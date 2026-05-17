# Stencil Islands — Inkscape extension

Find the parts of a stencil design that would **drop out** when it is cut on a
CNC laser, then **report**, **delete**, or **bridge** them.

A stencil has to be one continuous piece. Anything not connected to that piece
falls away when it is cut:

- the solid centre of letters such as **O, A, B, D, P, Q, R**, or the dot of
  **i / j** — a solid island floating inside a hole;
- a **detached shape** that was meant to be part of the same cuttable piece;
- (optionally) the disc of material inside a plain **counter** — e.g. an “O”
  drawn as just two circles — which the vector data doesn’t represent as a
  shape but which still physically falls out.

This extension detects all of those and lets you either remove them or tie
them back to the body with connectors in a variety of shapes.

Works on **Windows, macOS and Linux**, targets **Inkscape 1.2+**, and has
**no third-party dependencies** — all geometry is pure Python.

---

## How it works

Every closed subpath in the document is flattened to a polygon (each
element’s composed transform applied) and arranged into a containment forest.
Inkscape fills with the even-odd rule, so a ring’s nesting **depth** tells us
whether the region just inside it is solid or a hole:

| Depth | Meaning | Example |
|------:|---------|---------|
| 0 | Outermost solid (the body, or a separate solid blob) | outline of a letter |
| 1 | A hole / counter punched into that solid | the gap in an “O” |
| 2 | A **solid island** floating in a hole — drops out | the centre of an “O” drawn as 3 nested shapes |
| 3 | A hole again, and so on (parity continues) | |

Two things are reported as islands:

1. **enclosed** — a solid ring at even depth ≥ 2 (solid floating in a hole);
2. **separate** — a top-level solid piece that does not touch the main body
   (the main body is the largest connected piece, or the piece containing
   your selection).

With **Also flag bare counters** enabled, depth-1 holes with no inner shape
are reported as **counter** islands too.

### Bridges

A bridge is a connector that spans the shortest gap between an island and the
material it should hang off. It is added as a **filled shape that overlaps
both sides**. Run Inkscape’s native **Path ▸ Union** on the design plus the
generated bridge group and everything fuses into a single cuttable outline.
This is deliberate: it keeps the extension dependency-free instead of shipping
a polygon-boolean engine, and Inkscape’s own boolean ops are robust.

Connector shapes: `rectangle` (plain straight tie), `circle` (lozenge),
`hexagon`, `triangle` (a pinched bow tie), `blob` (rounded capsule). Width,
count (ties per island, spread evenly for big islands), and per-side overlap
are configurable.

---

## Install

### Quick (recommended)

```sh
python3 install.py            # copy into Inkscape's user extensions folder
python3 install.py --uninstall
python3 install.py --path     # just print the target folder
```

Restart Inkscape. The tool appears under **Extensions ▸ Stencil ▸ Find
Islands (Stencil Bridges)**.

### Manual

Copy these five files into your Inkscape user extensions directory:

```
stencil_islands.inx
stencil_islands.py
si_geometry.py
si_islands.py
si_bridges.py
```

| OS | Default extensions folder |
|----|---------------------------|
| Windows | `%APPDATA%\inkscape\extensions` |
| macOS | `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions` |
| Linux | `~/.config/inkscape/extensions` |

You can also see it from Inkscape: **Edit ▸ Preferences ▸ System ▸ User
extensions**.

---

## Usage

1. Open your stencil design.
2. **Extensions ▸ Stencil ▸ Find Islands (Stencil Bridges)**.
3. Keep **Live preview** ticked with **Action = Report** to see every island
   highlighted on the canvas. Tune **Ignore islands … area** to filter noise.
4. Switch **Action** to:
   - **Bridge** — pick a shape, width and count, click **Apply**, then select
     the design and the new `stencil-islands (bridges)` group and run
     **Path ▸ Union**.
   - **Delete** — removes the island geometry (separate blobs are removed
     whole; an island subpath inside a compound letter is dropped from that
     path). Bare counters are fixed by Delete (their hole is removed).

### Options

| Option | Meaning |
|--------|---------|
| Scope | Whole document or current selection only |
| Keep as the main piece | Largest connected piece, or the piece containing your selection |
| Ignore islands at or below this area | Noise filter, in px² |
| Also flag bare counters | Report depth-1 holes with no inner shape |
| Action | Report / Bridge / Delete |
| Bridge shape | rectangle / circle / hexagon / triangle / blob |
| Bridge width | Connector thickness (px) |
| Bridges per island | 1 = shortest gap; >1 spread evenly around the island |
| Bridge overlap each side | Extra length into each side (0 = auto) |
| Bridge fill | CSS hex, or `match` to copy the island’s fill |
| Highlight color | Report overlay colour |
| Curve flattening tolerance | Max chord error when sampling curves (px) |

---

## Limitations (v1)

- Bridges are emitted as overlapping shapes; you fuse them with one
  **Path ▸ Union**. The extension does not perform the boolean itself.
- For several disconnected pieces, each non-body piece is bridged toward the
  single nearest body ring rather than chained through a minimum spanning
  tree.
- **Bare counters** (an “O” as two bare circles) can be Deleted but not
  auto-bridged — a true counter bridge needs a gap routed through two
  concentric cut loops, which is planned but not in v1.
- Detection uses the even-odd fill model, matching Inkscape’s default
  rendering. Designs that rely on non-zero winding with self-intersecting
  paths may classify differently.

---

## Development

Pure-Python modules (`si_geometry.py`, `si_islands.py`, `si_bridges.py`) have
no Inkscape dependency and are unit-tested:

```sh
python3 -m pytest -q
```

CI runs the tests on Ubuntu, macOS and Windows across Python 3.9–3.12 and
validates the `.inx` is well-formed.

## License

GPL-2.0-or-later. See [LICENSE](LICENSE). `inkex`, which the runtime entry
point imports, is GPL-2.0-or-later.
