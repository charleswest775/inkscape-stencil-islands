#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bridge (tie) geometry for the Stencil Islands extension.

Pure Python, no Inkscape imports.

A *bridge* is a small connector that spans the shortest gap between an island
and the material it should hang off, so the island no longer drops out when
the design is laser-cut. We emit the connector as a filled polygon overlapping
both sides; one native ``Path > Union`` in Inkscape then fuses everything into
a single cuttable outline (this keeps the extension dependency-free instead of
shipping a polygon-boolean engine).

The connector outline can take several shapes so the join can be styled or
strengthened: ``rectangle`` (a plain straight tie), ``circle`` (a lozenge),
``hexagon``, ``triangle`` (a pinched/bow tie) and ``blob`` (a rounded
capsule). Every shape is generated to fit a capsule of the requested *length*
(gap + overlap on each side) and *width*, oriented along the gap.
"""

import math

from si_geometry import nearest_between_rings, resample_closed

SHAPES = ("rectangle", "circle", "hexagon", "triangle", "blob")


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    if n < 1e-12:
        return (1.0, 0.0)
    return (dx / n, dy / n)


def shape_polygon(shape, length, width, segments=24):
    """Connector outline centred at the origin, long axis along +x.

    The polygon spans ``[-length/2, +length/2]`` in x and is ``width`` thick
    in y. Returned points are open (no repeated first point).
    """
    half_l = max(length, 1e-6) / 2.0
    half_w = max(width, 1e-6) / 2.0

    if shape == "rectangle":
        return [
            (-half_l, -half_w),
            (half_l, -half_w),
            (half_l, half_w),
            (-half_l, half_w),
        ]

    if shape == "circle":
        # Ellipse (a lozenge stretched along the gap).
        pts = []
        for k in range(segments):
            ang = 2.0 * math.pi * k / segments
            pts.append((half_l * math.cos(ang), half_w * math.sin(ang)))
        return pts

    if shape == "hexagon":
        chamfer = min(half_w, half_l * 0.5)
        return [
            (-half_l, 0.0),
            (-half_l + chamfer, -half_w),
            (half_l - chamfer, -half_w),
            (half_l, 0.0),
            (half_l - chamfer, half_w),
            (-half_l + chamfer, half_w),
        ]

    if shape == "triangle":
        # A symmetric pinched "bow" tie: full width at both ends, waisted in
        # the middle. Stronger than a thin straight strip and clearly keyed.
        waist = half_w * 0.28
        return [
            (-half_l, -half_w),
            (0.0, -waist),
            (half_l, -half_w),
            (half_l, half_w),
            (0.0, waist),
            (-half_l, half_w),
        ]

    if shape == "blob":
        # Capsule: straight sides with semicircular end caps -> organic tie.
        pts = []
        cap_x = max(half_l - half_w, 0.0)
        steps = max(4, segments // 2)
        for k in range(steps + 1):  # right cap, -90deg -> +90deg
            ang = -math.pi / 2.0 + math.pi * k / steps
            pts.append((cap_x + half_w * math.cos(ang),
                        half_w * math.sin(ang)))
        for k in range(steps + 1):  # left cap, +90deg -> +270deg
            ang = math.pi / 2.0 + math.pi * k / steps
            pts.append((-cap_x + half_w * math.cos(ang),
                        half_w * math.sin(ang)))
        return pts

    raise ValueError("unknown bridge shape: {0!r}".format(shape))


def _place(local_pts, mid, direction):
    """Rotate *local_pts* (long axis +x) onto *direction* and move to *mid*."""
    ux, uy = direction
    out = []
    for x, y in local_pts:
        wx = mid[0] + x * ux - y * uy
        wy = mid[1] + x * uy + y * ux
        out.append((wx, wy))
    return out


def _connector_between(p_from, p_to, shape, width, overlap, segments):
    gap = math.hypot(p_to[0] - p_from[0], p_to[1] - p_from[1])
    direction = _unit(p_to[0] - p_from[0], p_to[1] - p_from[1])
    mid = ((p_from[0] + p_to[0]) / 2.0, (p_from[1] + p_to[1]) / 2.0)
    length = gap + 2.0 * max(overlap, 0.0)
    local = shape_polygon(shape, length, width, segments)
    return _place(local, mid, direction)


def make_connectors(
    island_points,
    anchor_points,
    shape="rectangle",
    width=1.0,
    count=1,
    overlap=None,
    segments=24,
):
    """Build connector polygons tying an island to its anchor ring.

    Returns ``(connectors, gap)`` where *connectors* is a list of point rings
    (world coordinates, ready to become SVG paths) and *gap* is the measured
    shortest distance between the two rings.

    With ``count == 1`` a single connector spans the shortest gap. With
    ``count > 1`` the connector positions are spread evenly (by arc length)
    around the island and each is tied to the nearest point on the anchor, so
    large islands are held in several places.
    """
    if not island_points or not anchor_points:
        return [], 0.0
    if overlap is None:
        overlap = max(width, 1.0)

    gap, p_isl, p_anc = nearest_between_rings(island_points, anchor_points)
    count = max(1, int(count))

    if count == 1:
        return (
            [_connector_between(p_isl, p_anc, shape, width, overlap, segments)],
            gap,
        )

    connectors = []
    for sample in resample_closed(island_points, count):
        _, _, near_anc = nearest_between_rings([sample], anchor_points)
        connectors.append(
            _connector_between(sample, near_anc, shape, width, overlap,
                               segments)
        )
    return connectors, gap


def points_to_path_d(points, close=True):
    """Serialise a point ring to an SVG path ``d`` string."""
    if not points:
        return ""
    head = "M {0:.6g} {1:.6g}".format(points[0][0], points[0][1])
    body = " ".join(
        "L {0:.6g} {1:.6g}".format(x, y) for x, y in points[1:]
    )
    out = (head + " " + body).strip()
    return out + " Z" if close else out
