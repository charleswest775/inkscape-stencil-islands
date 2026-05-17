# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit tests for bridge/connector geometry."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import si_bridges as b  # noqa: E402
from si_geometry import bbox, polygon_area  # noqa: E402


@pytest.mark.parametrize("shape", b.SHAPES)
def test_shape_polygon_fits_capsule(shape):
    pts = b.shape_polygon(shape, length=20.0, width=4.0)
    assert len(pts) >= 3
    minx, miny, maxx, maxy = bbox(pts)
    # Fits within the requested capsule and is non-degenerate.
    assert maxx <= 10.0 + 1e-6 and minx >= -10.0 - 1e-6
    assert maxy <= 2.0 + 1e-6 and miny >= -2.0 - 1e-6
    assert abs(polygon_area(pts)) > 1.0
    # Roughly centred on the origin.
    assert abs((minx + maxx) / 2.0) < 1e-6
    assert abs((miny + maxy) / 2.0) < 1e-6


def test_unknown_shape_raises():
    with pytest.raises(ValueError):
        b.shape_polygon("octagon", 10.0, 2.0)


def test_make_connectors_single_spans_gap():
    island = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    anchor = [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)]
    connectors, gap = b.make_connectors(
        island, anchor, shape="rectangle", width=2.0, overlap=1.0
    )
    assert abs(gap - 10.0) < 1e-6
    assert len(connectors) == 1
    minx, _, maxx, _ = bbox(connectors[0])
    # Length = gap + 2*overlap = 12, so it reaches into both sides.
    assert minx <= 10.0 + 1e-6
    assert maxx >= 20.0 - 1e-6
    assert abs((maxx - minx) - 12.0) < 1e-6


def test_make_connectors_multiple():
    island = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]
    anchor = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
    connectors, _ = b.make_connectors(
        island, anchor, shape="circle", width=2.0, count=3
    )
    assert len(connectors) == 3
    for poly in connectors:
        assert len(poly) >= 3


def test_make_connectors_auto_overlap_default():
    island = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    anchor = [(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)]
    # overlap=None -> auto = max(width, 1.0) = 3 -> length 10 + 2*3 = 16.
    connectors, _ = b.make_connectors(island, anchor, width=3.0)
    minx, _, maxx, _ = bbox(connectors[0])
    assert abs((maxx - minx) - 16.0) < 1e-6


def test_points_to_path_d():
    d = b.points_to_path_d([(0, 0), (1, 0), (1, 1)])
    assert d.startswith("M 0 0")
    assert " L 1 0" in d
    assert d.endswith("Z")
    assert b.points_to_path_d([]) == ""
    assert not b.points_to_path_d([(0, 0), (1, 1)], close=False).endswith("Z")


def test_empty_inputs_safe():
    connectors, gap = b.make_connectors([], [(0, 0), (1, 0), (1, 1)])
    assert connectors == [] and gap == 0.0
