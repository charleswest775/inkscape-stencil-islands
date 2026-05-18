#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stencil Islands: find parts that drop out of a laser-cut stencil and either
report, delete, or bridge them.

An *island* is material that is not connected to the one continuous piece you
want to keep, so it falls away when the design is cut:

* the solid centre of letters like O, A, B, D (an island floating in a hole);
* a detached shape that should be part of the same cuttable piece;
* (optionally) the unrepresented disc inside a plain counter such as an O
  drawn as two bare circles.

Detection and bridge geometry live in the pure-Python ``si_*`` modules so they
can be unit-tested without Inkscape. This file is only the inkex glue: it
flattens the document to rings (each element's composed transform applied),
runs detection, and applies the chosen action.

Bridges are emitted as filled connector shapes overlapping both sides. Run
Inkscape's native ``Path > Union`` on the design plus the bridge group to fuse
everything into a single cuttable outline (this is why the extension needs no
polygon-boolean dependency).
"""

import inkex
from inkex import Style
from inkex.paths import CubicSuperPath

from si_bridges import make_connectors, points_to_path_d
from si_geometry import bbox, flatten_superpath
from si_islands import (
    COUNTER,
    SEPARATE,
    build_forest,
    build_rings,
    detect_islands,
    summarize,
)

SHAPE_TYPES = (
    inkex.PathElement,
    inkex.Rectangle,
    inkex.Circle,
    inkex.Ellipse,
    inkex.Line,
    inkex.Polyline,
    inkex.Polygon,
)


class StencilIslands(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--tab", default="options")
        pars.add_argument("--scope", default="all", help="all | selection")
        pars.add_argument(
            "--main_body", default="largest", help="largest | selection"
        )
        pars.add_argument("--min_area", type=float, default=1.0)
        pars.add_argument(
            "--include_counters", type=inkex.Boolean, default=False
        )
        pars.add_argument(
            "--mode", default="report", help="report | delete | bridge"
        )
        pars.add_argument(
            "--bridge_shape",
            default="rectangle",
            help="rectangle | circle | hexagon | triangle | blob",
        )
        pars.add_argument("--bridge_width", type=float, default=1.5)
        pars.add_argument("--bridge_count", type=int, default=1)
        pars.add_argument("--bridge_overlap", type=float, default=0.0)
        pars.add_argument("--bridge_color", default="#19a974")
        pars.add_argument("--highlight_color", default="#ff00ff")
        pars.add_argument("--curve_tolerance", type=float, default=0.25)
        # Off by default: writing to stderr makes Inkscape pop the "received
        # additional data from the script" dialog on every live-preview run.
        pars.add_argument(
            "--show_summary", type=inkex.Boolean, default=False
        )

    # --- collection ---------------------------------------------------------

    def _roots(self):
        if self.options.scope == "selection" and len(self.svg.selection):
            return list(self.svg.selection.values())
        return [self.svg]

    def _shapes(self):
        seen = set()
        for root in self._roots():
            for elem in root.iter():
                if not isinstance(elem, SHAPE_TYPES):
                    continue
                key = id(elem)
                if key in seen:
                    continue
                seen.add(key)
                yield elem

    def _selection_ids(self):
        ids = set()
        try:
            for elem in self.svg.selection.values():
                ids.add(elem.get_id())
        except Exception:
            pass
        return ids

    # --- main ---------------------------------------------------------------

    def effect(self):
        tol = max(0.01, float(self.options.curve_tolerance))
        flattened = []
        elem_by_id = {}
        local_csp_by_id = {}

        for elem in self._shapes():
            try:
                abs_path = elem.path.transform(elem.composed_transform())
                abs_csp = abs_path.to_superpath()
                local_csp = elem.path.to_superpath()
            except Exception:
                continue
            if not abs_csp:
                continue
            eid = elem.get_id()
            elem_by_id[eid] = elem
            local_csp_by_id[eid] = local_csp
            for idx, pts in enumerate(flatten_superpath(abs_csp, tol)):
                flattened.append((eid, idx, pts))

        rings = build_forest(build_rings(flattened))
        islands = detect_islands(
            rings,
            main_body=self.options.main_body,
            selection_ids=self._selection_ids(),
            min_area=max(0.0, float(self.options.min_area)),
            include_counters=bool(self.options.include_counters),
        )

        if not islands:
            self._summary(summarize(islands))
            return

        mode = self.options.mode
        if mode == "delete":
            note = self._do_delete(islands, elem_by_id, local_csp_by_id)
        elif mode == "bridge":
            note = self._do_bridge(islands, elem_by_id)
        else:
            note = self._do_report(islands, rings)

        self._summary(summarize(islands) + " " + note)

    def _summary(self, text):
        """Emit the status line only when the user opted in.

        inkex's ``msg`` writes to stderr, and Inkscape shows any stderr from
        an effect in a modal "received additional data" dialog - which fires
        on every live-preview re-run. Keeping this off by default makes the
        normal/preview path completely silent.
        """
        if self.options.show_summary:
            self.msg("Stencil Islands: " + text)

    # --- actions ------------------------------------------------------------

    def _new_group(self, label):
        group = inkex.Group()
        group.set("inkscape:label", label)
        group.set("id", self.svg.get_unique_id("stencil-islands"))
        self.svg.get_current_layer().add(group)
        return group

    def _doc_stroke(self):
        """A stroke width that stays visible across very different doc sizes."""
        try:
            box = self.svg.get_page_bbox()
            diag = (box.width ** 2 + box.height ** 2) ** 0.5
            if diag > 0:
                return max(0.25, diag * 0.0025)
        except Exception:
            pass
        return 1.0

    def _do_report(self, islands, rings):
        group = self._new_group("stencil-islands (highlight)")
        sw = self._doc_stroke()
        for isl in islands:
            overlay = inkex.PathElement()
            overlay.set("d", points_to_path_d(isl.ring.points))
            overlay.style = Style(
                {
                    "fill": self.options.highlight_color,
                    "fill-opacity": "0.35",
                    "stroke": self.options.highlight_color,
                    "stroke-width": "{0:.4g}".format(sw),
                    "stroke-opacity": "1",
                }
            )
            overlay.set("inkscape:label", "island ({0})".format(isl.kind))
            group.add(overlay)
        return (
            "Highlighted (non-destructive). Re-run with Action = Delete or "
            "Bridge to act on them."
        )

    def _do_delete(self, islands, elem_by_id, local_csp_by_id):
        # Whole separate blobs: delete the source element outright.
        # Enclosed/counter subpaths: drop just that subpath from its element.
        whole = set()
        per_subpath = {}
        for isl in islands:
            eid = isl.ring.element_id
            if isl.kind == SEPARATE:
                whole.add(eid)
            else:
                per_subpath.setdefault(eid, set()).add(
                    isl.ring.subpath_index
                )

        removed = 0
        for eid in whole:
            elem = elem_by_id.get(eid)
            if elem is not None:
                try:
                    elem.delete()
                    removed += 1
                except Exception:
                    pass

        for eid, idxs in per_subpath.items():
            if eid in whole:
                continue
            elem = elem_by_id.get(eid)
            csp = local_csp_by_id.get(eid)
            if elem is None or csp is None:
                continue
            kept = [sp for i, sp in enumerate(csp) if i not in idxs]
            removed += len(csp) - len(kept)
            try:
                if not kept:
                    elem.delete()
                else:
                    elem.set("d", str(CubicSuperPath(kept).to_path()))
            except Exception:
                pass
        return "Deleted {0} island path(s).".format(removed)

    def _do_bridge(self, islands, elem_by_id):
        group = self._new_group("stencil-islands (bridges)")
        width = max(1e-3, float(self.options.bridge_width))
        count = max(1, int(self.options.bridge_count))
        overlap = float(self.options.bridge_overlap)
        overlap = None if overlap <= 0 else overlap
        shape = self.options.bridge_shape

        made = 0
        skipped = 0
        for isl in islands:
            if isl.anchor is None or isl.kind == COUNTER:
                # A bare counter has no inner solid to tie to; deleting the
                # inner ring (Action = Delete) is the correct fix instead.
                skipped += 1
                continue
            connectors, _gap = make_connectors(
                isl.ring.points,
                isl.anchor.points,
                shape=shape,
                width=width,
                count=count,
                overlap=overlap,
            )
            fill = self._bridge_fill(isl, elem_by_id)
            for poly in connectors:
                bridge = inkex.PathElement()
                bridge.set("d", points_to_path_d(poly))
                bridge.style = Style(
                    {"fill": fill, "stroke": "none", "fill-opacity": "1"}
                )
                bridge.set("inkscape:label", "bridge")
                group.add(bridge)
                made += 1

        hint = (
            "Added {0} connector(s). Select the design and this bridge group, "
            "then Path > Union to fuse into one cuttable outline.".format(made)
        )
        if skipped:
            hint += (
                " Skipped {0} bare counter(s) - use Action = Delete on those."
                .format(skipped)
            )
        return hint

    def _bridge_fill(self, isl, elem_by_id):
        color = self.options.bridge_color
        if color != "match":
            return color
        elem = elem_by_id.get(isl.ring.element_id)
        if elem is not None:
            try:
                fill = elem.style.get("fill")
                if fill and fill != "none":
                    return fill
            except Exception:
                pass
        return "#19a974"


if __name__ == "__main__":
    StencilIslands().run()
