# SPDX-License-Identifier: GPL-2.0-or-later
"""End-to-end tests through inkex. Skipped automatically where inkex is not
installed (e.g. a bare dev machine); CI installs inkex so they run there."""

import io
import pathlib
import sys

import pytest

pytest.importorskip("inkex")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from stencil_islands import StencilIslands  # noqa: E402

# "ring" is a compound path: outer solid (depth 0, the body), a hole
# (depth 1), and a solid island (depth 2). "loose" is a detached square
# (a separate piece). "ohole" is a bare counter (solid + hole, no inner).
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"
viewBox="0 0 400 400">
  <path id="ring" d="M 10 10 H 110 V 110 H 10 Z
                      M 30 30 H 90 V 90 H 30 Z
                      M 45 45 H 75 V 75 H 45 Z"/>
  <rect id="loose" x="200" y="200" width="30" height="30"/>
  <path id="ohole" d="M 250 20 H 320 V 90 H 250 Z
                      M 270 40 H 300 V 70 H 270 Z"/>
</svg>"""


def run_ext(tmp_path, args, svg=SVG):
    src = tmp_path / "in.svg"
    src.write_text(svg)
    out = io.BytesIO()
    try:
        StencilIslands().run(args + [str(src)], output=out)
    except SystemExit:
        pass
    return out.getvalue().decode("utf-8")


def test_report_is_non_destructive(tmp_path):
    result = run_ext(tmp_path, ["--mode=report"])
    assert 'id="ring"' in result
    assert 'id="loose"' in result
    assert "stencil-islands (highlight)" in result


def test_delete_removes_island_and_separate(tmp_path):
    result = run_ext(tmp_path, ["--mode=delete", "--min_area=1"])
    # The detached square is removed entirely.
    assert 'id="loose"' not in result
    # The compound letter survives (only its depth-2 subpath is dropped).
    assert 'id="ring"' in result


def test_bridge_adds_connector_group(tmp_path):
    result = run_ext(
        tmp_path,
        ["--mode=bridge", "--bridge_shape=hexagon", "--bridge_width=2"],
    )
    assert "stencil-islands (bridges)" in result
    # inkex may serialise inkscape:label under a generic ns prefix; match
    # the namespace-agnostic tail.
    assert 'label="bridge"' in result
    # Original geometry is untouched by bridging.
    assert 'id="ring"' in result and 'id="loose"' in result


def test_counter_flag_changes_count(tmp_path):
    plain = run_ext(tmp_path, ["--mode=report"])
    with_counter = run_ext(
        tmp_path, ["--mode=report", "--include_counters=true"]
    )
    # Enabling counters reports strictly more islands (the bare "ohole").
    assert with_counter.count('label="island') > \
        plain.count('label="island')
