# Changelog

## 0.1.0 — unreleased

Initial release.

- Detect stencil islands: enclosed solid islands (even depth ≥ 2), separate
  top-level pieces that don't touch the main body, and (optional) bare
  counters.
- Containment forest + even-odd depth model; pure-Python geometry with no
  third-party or Inkscape dependencies in the algorithm modules.
- Actions: Report/highlight (non-destructive), Delete, Bridge.
- Bridge connector shapes: rectangle, circle, hexagon, triangle, blob;
  configurable width, count (spread evenly around large islands) and overlap.
- Cross-platform installer (`install.py`) for Windows, macOS and Linux.
- Deterministic demo/regression fixture in `examples/known-islands.svg`.
- CI on Ubuntu/macOS/Windows across Python 3.9–3.12; test suite verified
  green against inkex 1.4.1 + numpy 2.x (the modern Inkscape line).
