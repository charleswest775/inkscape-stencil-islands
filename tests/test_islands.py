# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit tests for island detection (containment forest + classification)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from si_islands import (  # noqa: E402
    COUNTER,
    ENCLOSED,
    SEPARATE,
    build_forest,
    build_rings,
    detect_islands,
    summarize,
)


def sq(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def forest(flattened):
    return build_forest(build_rings(flattened))


def test_single_shape_has_no_islands():
    rings = forest([("a", 0, sq(0, 0, 100, 100))])
    assert detect_islands(rings) == []
    assert "No islands" in summarize([])


def test_enclosed_solid_island():
    # Three nested squares: solid / hole / solid-island.
    rings = forest([
        ("o", 0, sq(0, 0, 100, 100)),    # depth 0 solid (body)
        ("o", 1, sq(20, 20, 80, 80)),    # depth 1 hole
        ("o", 2, sq(35, 35, 65, 65)),    # depth 2 solid -> island
    ])
    islands = detect_islands(rings)
    assert len(islands) == 1
    isl = islands[0]
    assert isl.kind == ENCLOSED
    assert isl.depth == 2
    assert isl.ring.subpath_index == 2
    # Bridges to its parent hole boundary.
    assert isl.anchor is not None
    assert isl.anchor.subpath_index == 1


def test_separate_piece_is_island_largest_is_body():
    rings = forest([
        ("big", 0, sq(0, 0, 100, 100)),     # area 10000 -> body
        ("small", 0, sq(200, 200, 230, 230)),  # area 900, detached
    ])
    islands = detect_islands(rings)
    assert len(islands) == 1
    assert islands[0].kind == SEPARATE
    assert islands[0].ring.element_id == "small"
    assert islands[0].anchor.element_id == "big"


def test_main_body_by_selection_flips_which_is_island():
    rings = forest([
        ("big", 0, sq(0, 0, 100, 100)),
        ("small", 0, sq(200, 200, 230, 230)),
    ])
    islands = detect_islands(
        rings, main_body="selection", selection_ids={"small"}
    )
    assert len(islands) == 1
    assert islands[0].ring.element_id == "big"  # big now drops out


def test_counter_only_with_flag():
    rings = forest([
        ("o", 0, sq(0, 0, 100, 100)),   # solid
        ("o", 1, sq(30, 30, 70, 70)),   # hole, no inner ring -> bare counter
    ])
    assert detect_islands(rings) == []
    flagged = detect_islands(rings, include_counters=True)
    assert len(flagged) == 1
    assert flagged[0].kind == COUNTER


def test_min_area_filter():
    rings = forest([
        ("o", 0, sq(0, 0, 100, 100)),
        ("o", 1, sq(40, 40, 60, 60)),     # hole
        ("o", 2, sq(49, 49, 51, 51)),     # tiny island, area 4
    ])
    assert len(detect_islands(rings, min_area=0.0)) == 1
    assert detect_islands(rings, min_area=10.0) == []


def test_summarize_counts_kinds():
    rings = forest([
        ("big", 0, sq(0, 0, 100, 100)),
        ("a", 0, sq(200, 0, 230, 30)),
        ("b", 0, sq(300, 0, 330, 30)),
    ])
    islands = detect_islands(rings)
    text = summarize(islands)
    assert "2 island(s)" in text
    assert "separate" in text
