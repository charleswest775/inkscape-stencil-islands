# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit tests for the pure-Python geometry layer."""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import si_geometry as g  # noqa: E402

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
# A concave "C": a square with a deep notch bitten out of the right side.
C_SHAPE = [
    (0.0, 0.0), (10.0, 0.0), (10.0, 3.0), (3.0, 3.0),
    (3.0, 7.0), (10.0, 7.0), (10.0, 10.0), (0.0, 10.0),
]


def test_polygon_area_and_bbox():
    assert abs(abs(g.polygon_area(SQUARE)) - 100.0) < 1e-9
    # Reversing winding flips the sign but not the magnitude.
    assert g.polygon_area(SQUARE) == -g.polygon_area(list(reversed(SQUARE)))
    assert g.bbox(SQUARE) == (0.0, 0.0, 10.0, 10.0)
    assert g.bbox_area((0.0, 0.0, 10.0, 4.0)) == 40.0


def test_bboxes_overlap():
    assert g.bboxes_overlap((0, 0, 10, 10), (5, 5, 15, 15))
    assert not g.bboxes_overlap((0, 0, 10, 10), (20, 20, 30, 30))
    assert g.bboxes_overlap((0, 0, 10, 10), (12, 0, 20, 10), pad=3)


def test_point_in_polygon():
    assert g.point_in_polygon((5.0, 5.0), SQUARE)
    assert not g.point_in_polygon((50.0, 5.0), SQUARE)
    # A point inside the notch of the C is outside the polygon.
    assert not g.point_in_polygon((6.0, 5.0), C_SHAPE)
    assert g.point_in_polygon((1.0, 5.0), C_SHAPE)


def test_representative_point_is_inside_concave():
    p = g.representative_point(C_SHAPE)
    assert g.point_in_polygon(p, C_SHAPE)
    # Centroid of the C lands in the notch, so this must not be the centroid.
    assert not g.point_in_polygon(g.polygon_centroid(C_SHAPE), C_SHAPE)


def test_segments_intersect():
    assert g.segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))   # cross
    assert not g.segments_intersect((0, 0), (10, 0), (0, 5), (10, 5))  # parallel
    assert g.segments_intersect((0, 0), (10, 0), (10, 0), (10, 10))    # touch
    assert g.segments_intersect((0, 0), (10, 0), (5, 0), (15, 0))      # collinear


def test_rings_touch():
    a = SQUARE
    overlapping = [(5, 5), (15, 5), (15, 15), (5, 15)]
    disjoint = [(20, 20), (30, 20), (30, 30), (20, 30)]
    nested = [(2, 2), (8, 2), (8, 8), (2, 8)]
    assert g.rings_touch(a, overlapping)
    assert not g.rings_touch(a, disjoint)
    assert g.rings_touch(a, nested)  # one fully contains the other


def test_nearest_between_rings():
    a = SQUARE
    b = [(20, 0), (30, 0), (30, 10), (20, 10)]  # 10 units to the right
    d, pa, pb = g.nearest_between_rings(a, b)
    assert abs(d - 10.0) < 1e-6
    assert abs(pa[0] - 10.0) < 1e-6
    assert abs(pb[0] - 20.0) < 1e-6


def test_resample_closed():
    ring = [(0, 0), (4, 0), (4, 4), (0, 4)]  # perimeter 16
    pts = g.resample_closed(ring, 4)
    assert len(pts) == 4
    for got, want in zip(pts, [(0, 0), (4, 0), (4, 4), (0, 4)]):
        assert math.hypot(got[0] - want[0], got[1] - want[1]) < 1e-6


def test_parse_path_polygon():
    subs = g.parse_path("M 0 0 L 10 0 L 10 10 L 0 10 Z")
    assert len(subs) == 1
    assert subs[0].closed
    assert abs(abs(g.polygon_area(subs[0].points)) - 100.0) < 1e-9


def test_parse_path_relative_hv():
    subs = g.parse_path("m 0 0 h 10 v 10 h -10 z")
    assert abs(abs(g.polygon_area(subs[0].points)) - 100.0) < 1e-9


def test_parse_path_circle_arc_area():
    # Full circle r=10 as two semicircle arcs; area ~= pi r^2.
    d = "M 10 0 A 10 10 0 1 0 -10 0 A 10 10 0 1 0 10 0 Z"
    subs = g.parse_path(d, tolerance=0.02)
    area = abs(g.polygon_area(subs[0].points))
    assert abs(area - math.pi * 100.0) < 2.0


def test_parse_path_cubic_and_quadratic():
    # A cubic whose controls lie on the chord is a straight line.
    subs = g.parse_path("M 0 0 C 3 0 6 0 9 0 Q 9 9 0 9 Z")
    assert len(subs) == 1
    assert len(subs[0].points) >= 3


def test_flatten_superpath_square():
    knot = lambda x, y: [[x, y], [x, y], [x, y]]  # noqa: E731
    csp = [[knot(0, 0), knot(10, 0), knot(10, 10), knot(0, 10), knot(0, 0)]]
    subs = g.flatten_superpath(csp)
    assert len(subs) == 1
    assert abs(abs(g.polygon_area(subs[0])) - 100.0) < 1e-9
