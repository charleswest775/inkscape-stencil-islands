#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stencil island detection.

Pure Python, no Inkscape imports, so the whole detection pipeline is
unit-testable on a bare interpreter.

Model
-----
A stencil design is a set of closed paths. We flatten every subpath to a
*ring* and build a containment forest (which ring is nested inside which).
Inkscape paints fills with the even-odd rule, so a ring's *depth* (number of
ancestors) tells us whether the region just inside it is solid material or a
hole:

* depth 0  -> outermost solid (the body / a separate solid blob)
* depth 1  -> a hole / counter punched into that solid (e.g. the gap of an O)
* depth 2  -> a *solid island* floating inside a hole - attached to nothing,
              it physically drops out when cut. This is the classic stencil
              island (centre of O/A/B/D, dot of i/j, ...).
* depth 3  -> a hole again, and so on (parity continues).

Two kinds of thing "drop out" and are reported as islands:

1. **enclosed** - a solid ring at even depth >= 2 (solid floating in a hole).
2. **separate** - a top-level (depth 0) solid blob that does not touch the
   main body. Several detached letters/shapes that should be one cuttable
   piece each fall into this bucket.

Optionally (``include_counters``) we also flag **counter** holes: a depth-1
void whose parent is solid and which contains no further ring. The disc of
material inside it (think: the centre of an O drawn as just two circles) is
unrepresented in the vector data but will physically fall out.
"""

from si_geometry import (
    bbox,
    bbox_area,
    bboxes_overlap,
    nearest_between_rings,
    point_in_polygon,
    polygon_area,
    representative_point,
    rings_touch,
)

# Island kinds.
ENCLOSED = "enclosed"
SEPARATE = "separate"
COUNTER = "counter"


class Ring(object):
    """One flattened closed subpath plus its place in the containment forest."""

    __slots__ = (
        "element_id",
        "subpath_index",
        "points",
        "signed_area",
        "abs_area",
        "box",
        "rep",
        "parent",
        "children",
        "depth",
    )

    def __init__(self, element_id, subpath_index, points):
        self.element_id = element_id
        self.subpath_index = subpath_index
        self.points = points
        self.signed_area = polygon_area(points)
        self.abs_area = abs(self.signed_area)
        self.box = bbox(points)
        self.rep = representative_point(points)
        self.parent = None        # Ring or None
        self.children = []        # list[Ring]
        self.depth = 0            # number of ancestors

    @property
    def is_solid(self):
        """Even-odd: even depth = solid material, odd depth = hole."""
        return self.depth % 2 == 0

    def __repr__(self):
        return "<Ring {0}#{1} depth={2} area={3:.3g}>".format(
            self.element_id, self.subpath_index, self.depth, self.abs_area
        )


class Island(object):
    """A detected drop-out, plus where to attach a bridge."""

    __slots__ = ("ring", "kind", "anchor", "depth", "area")

    def __init__(self, ring, kind, anchor, depth, area):
        self.ring = ring          # the Ring that drops out
        self.kind = kind          # ENCLOSED | SEPARATE | COUNTER
        self.anchor = anchor      # Ring to bridge to (None if N/A)
        self.depth = depth
        self.area = area

    def __repr__(self):
        return "<Island {0} {1} area={2:.3g}>".format(
            self.kind, self.ring, self.area
        )


def build_rings(flattened):
    """Build :class:`Ring` objects from ``(element_id, index, points)`` tuples.

    Rings with fewer than 3 points or negligible area are dropped: they are
    cut artefacts, not regions that can contain or drop out.
    """
    rings = []
    for element_id, idx, points in flattened:
        if len(points) < 3:
            continue
        ring = Ring(element_id, idx, points)
        if ring.abs_area <= 1e-6:
            continue
        rings.append(ring)
    return rings


def build_forest(rings):
    """Populate ``parent``/``children``/``depth`` for every ring.

    A ring's parent is the *smallest-area* ring that strictly contains it,
    tested with a representative interior point (bounding boxes prune the
    obvious non-containments first).
    """
    for child in rings:
        best = None
        for cand in rings:
            if cand is child:
                continue
            if cand.abs_area <= child.abs_area:
                continue
            if not bboxes_overlap(cand.box, child.box):
                continue
            if not point_in_polygon(child.rep, cand.points):
                continue
            if best is None or cand.abs_area < best.abs_area:
                best = cand
        child.parent = best

    for child in rings:
        if child.parent is not None:
            child.parent.children.append(child)
        depth = 0
        node = child.parent
        while node is not None:
            depth += 1
            node = node.parent
        child.depth = depth
    return rings


def _components(top_rings):
    """Union-find over depth-0 rings that touch -> list of components."""
    parent = list(range(len(top_rings)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    n = len(top_rings)
    for i in range(n):
        for k in range(i + 1, n):
            if bboxes_overlap(top_rings[i].box, top_rings[k].box) and (
                rings_touch(top_rings[i].points, top_rings[k].points)
            ):
                union(i, k)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(top_rings[i])
    return list(groups.values())


def detect_islands(
    rings,
    main_body="largest",
    selection_ids=None,
    min_area=0.0,
    include_counters=False,
):
    """Return a list of :class:`Island` objects.

    Parameters
    ----------
    rings : list[Ring]
        Already passed through :func:`build_forest`.
    main_body : "largest" | "selection"
        How to pick the piece that everything else should hang off. With
        ``"selection"`` the body is the component containing any ring whose
        ``element_id`` is in *selection_ids*.
    selection_ids : set[str] | None
        Source element ids the user had selected (used by ``"selection"``).
    min_area : float
        Ignore islands whose absolute area is at or below this (noise filter).
    include_counters : bool
        Also flag enclosed depth-1 voids (potential physical drop-outs that
        the vector data does not represent as a solid).
    """
    selection_ids = selection_ids or set()
    top = [r for r in rings if r.depth == 0]
    comps = _components(top)
    if not comps:
        return []

    def comp_area(group):
        return sum(g.abs_area for g in group)

    body = None
    if main_body == "selection" and selection_ids:
        for group in comps:
            if any(g.element_id in selection_ids for g in group):
                body = group
                break
    if body is None:
        body = max(comps, key=comp_area)
    body_set = set(id(g) for g in body)

    islands = []

    # 1. Separate top-level blobs that are not the main body.
    for group in comps:
        if any(id(g) in body_set for g in group):
            continue
        rep_ring = max(group, key=lambda r: r.abs_area)
        if rep_ring.abs_area <= min_area:
            continue
        anchor = _nearest_ring(rep_ring, body)
        islands.append(
            Island(rep_ring, SEPARATE, anchor, rep_ring.depth, rep_ring.abs_area)
        )

    # 2. Enclosed solid islands: solid (even depth) at depth >= 2.
    for ring in rings:
        if ring.depth >= 2 and ring.is_solid:
            if ring.abs_area <= min_area:
                continue
            islands.append(
                Island(ring, ENCLOSED, ring.parent, ring.depth, ring.abs_area)
            )

    # 3. Optional: counter holes with no inner ring (unrepresented drop-out).
    if include_counters:
        for ring in rings:
            if ring.depth == 1 and not ring.is_solid and not ring.children:
                if ring.abs_area <= min_area:
                    continue
                islands.append(
                    Island(ring, COUNTER, ring.parent, ring.depth,
                           ring.abs_area)
                )

    islands.sort(key=lambda isl: isl.area, reverse=True)
    return islands


def _nearest_ring(ring, group):
    """The ring in *group* closest to *ring* (bbox-centre heuristic, then
    exact nearest-point refinement on the best few)."""
    if not group:
        return None
    rx = (ring.box[0] + ring.box[2]) / 2.0
    ry = (ring.box[1] + ring.box[3]) / 2.0

    def centre_d2(g):
        gx = (g.box[0] + g.box[2]) / 2.0
        gy = (g.box[1] + g.box[3]) / 2.0
        return (gx - rx) ** 2 + (gy - ry) ** 2

    ordered = sorted(group, key=centre_d2)
    best = None
    best_d = float("inf")
    for cand in ordered[:4]:
        d, _, _ = nearest_between_rings(ring.points, cand.points)
        if d < best_d:
            best_d = d
            best = cand
    return best


def summarize(islands):
    """Human-readable one-liner used by the extension's status message."""
    if not islands:
        return "No islands found - the design is one connected piece."
    by_kind = {}
    for isl in islands:
        by_kind[isl.kind] = by_kind.get(isl.kind, 0) + 1
    parts = ["{0} {1}".format(v, k) for k, v in sorted(by_kind.items())]
    return "{0} island(s): {1}.".format(len(islands), ", ".join(parts))
