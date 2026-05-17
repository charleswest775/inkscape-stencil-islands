#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pure-Python 2-D geometry for the Stencil Islands extension.

No third-party dependencies and no Inkscape imports, so every routine here is
unit-testable on a bare Python install and works identically on Windows,
macOS and Linux.

A *ring* is a list of ``(x, y)`` float tuples describing a closed polygon. The
closing edge (last point back to first) is implied; callers must not repeat the
first point at the end.

All coordinates are in the SVG document user space (y grows downward). Only the
relative sign of areas matters to the algorithms that use them, so the y-down
convention is harmless as long as it is applied consistently.
"""

import math

# Distance below which two coordinates are considered the same point.
EPS = 1e-9


# --------------------------------------------------------------------------- #
# Basic polygon measures
# --------------------------------------------------------------------------- #

def polygon_area(ring):
    """Signed area of *ring* via the shoelace formula.

    The magnitude is the enclosed area; the sign encodes winding direction
    (consistent within one document, which is all the caller needs).
    """
    n = len(ring)
    if n < 3:
        return 0.0
    acc = 0.0
    x0, y0 = ring[-1]
    for x1, y1 in ring:
        acc += x0 * y1 - x1 * y0
        x0, y0 = x1, y1
    return acc / 2.0


def polygon_centroid(ring):
    """Area-weighted centroid of *ring*; falls back to the vertex mean for
    degenerate (zero-area) rings."""
    n = len(ring)
    if n == 0:
        return (0.0, 0.0)
    a = polygon_area(ring)
    if abs(a) < EPS:
        sx = sum(p[0] for p in ring) / n
        sy = sum(p[1] for p in ring) / n
        return (sx, sy)
    cx = cy = 0.0
    x0, y0 = ring[-1]
    for x1, y1 in ring:
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
        x0, y0 = x1, y1
    factor = 1.0 / (6.0 * a)
    return (cx * factor, cy * factor)


def bbox(ring):
    """Axis-aligned bounding box ``(minx, miny, maxx, maxy)`` of *ring*."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def bboxes_overlap(a, b, pad=0.0):
    """True if boxes *a* and *b* overlap (optionally grown by *pad*)."""
    return not (
        a[2] + pad < b[0]
        or b[2] + pad < a[0]
        or a[3] + pad < b[1]
        or b[3] + pad < a[1]
    )


def perimeter(ring):
    n = len(ring)
    if n < 2:
        return 0.0
    total = 0.0
    x0, y0 = ring[-1]
    for x1, y1 in ring:
        total += math.hypot(x1 - x0, y1 - y0)
        x0, y0 = x1, y1
    return total


# --------------------------------------------------------------------------- #
# Point / polygon predicates
# --------------------------------------------------------------------------- #

def point_in_polygon(pt, ring):
    """Even-odd ray-cast test: is *pt* strictly inside *ring*?

    Points exactly on an edge are reported as inside, which is fine because
    callers always probe with deliberately interior representative points.
    """
    x, y = pt
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if _on_segment(pt, ring[j], ring[i]):
            return True
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _on_segment(p, a, b):
    """True if point *p* lies on the closed segment *a*-*b*."""
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if abs(cross) > 1e-7 * (1.0 + abs(b[0] - a[0]) + abs(b[1] - a[1])):
        return False
    if min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS and (
        min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS
    ):
        return True
    return False


def representative_point(ring):
    """Return a point guaranteed to lie inside *ring*.

    Tries the centroid first (correct for convex and many concave shapes);
    otherwise scans horizontal chords and returns the midpoint of the widest
    interior span, nudging the scan line off vertices when needed.
    """
    c = polygon_centroid(ring)
    if point_in_polygon(c, ring):
        return c
    minx, miny, maxx, maxy = bbox(ring)
    height = maxy - miny or 1.0
    for frac in (0.5, 0.4, 0.6, 0.3, 0.7, 0.25, 0.75, 0.45, 0.55):
        y = miny + height * frac
        xs = _scanline_x(ring, y)
        best = None
        for k in range(0, len(xs) - 1, 2):
            x_lo, x_hi = xs[k], xs[k + 1]
            width = x_hi - x_lo
            if best is None or width > best[0]:
                best = (width, (x_lo + x_hi) / 2.0)
        if best is not None and best[0] > EPS:
            cand = (best[1], y)
            if point_in_polygon(cand, ring):
                return cand
    return c  # last resort; degenerate ring


def _scanline_x(ring, y):
    """Sorted x-coordinates where ring edges cross the horizontal line *y*."""
    xs = []
    n = len(ring)
    j = n - 1
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[j]
        if (y1 > y) != (y2 > y):
            xs.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)
        j = i
    xs.sort()
    return xs


# --------------------------------------------------------------------------- #
# Segment / ring intersection
# --------------------------------------------------------------------------- #

def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if v > EPS:
        return 1
    if v < -EPS:
        return -1
    return 0


def segments_intersect(p1, p2, p3, p4):
    """True if segment *p1p2* intersects segment *p3p4* (incl. touching)."""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    if d1 != d2 and d3 != d4:
        return True
    if d1 == 0 and _on_segment(p1, p3, p4):
        return True
    if d2 == 0 and _on_segment(p2, p3, p4):
        return True
    if d3 == 0 and _on_segment(p3, p1, p2):
        return True
    if d4 == 0 and _on_segment(p4, p1, p2):
        return True
    return False


def rings_touch(ring_a, ring_b):
    """True if the closed polylines *ring_a* and *ring_b* share any point
    (edges crossing, or one fully containing the other)."""
    ba = bbox(ring_a)
    bb = bbox(ring_b)
    if not bboxes_overlap(ba, bb):
        return False
    na, nb = len(ring_a), len(ring_b)
    for i in range(na):
        a1 = ring_a[i]
        a2 = ring_a[(i + 1) % na]
        for k in range(nb):
            b1 = ring_b[k]
            b2 = ring_b[(k + 1) % nb]
            if segments_intersect(a1, a2, b1, b2):
                return True
    # No edge crossings: still "touching" if one encloses the other.
    if point_in_polygon(ring_a[0], ring_b) or point_in_polygon(
        ring_b[0], ring_a
    ):
        return True
    return False


# --------------------------------------------------------------------------- #
# Distances / nearest points (used for bridge placement)
# --------------------------------------------------------------------------- #

def closest_point_on_segment(p, a, b):
    """Closest point to *p* on segment *a*-*b*, plus the squared distance."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom < EPS:
        return (ax, ay), (p[0] - ax) ** 2 + (p[1] - ay) ** 2
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return (cx, cy), (p[0] - cx) ** 2 + (p[1] - cy) ** 2


def nearest_between_rings(ring_a, ring_b):
    """Approximate nearest pair of points between two rings.

    Returns ``(distance, point_on_a, point_on_b)``. Each vertex of one ring is
    projected onto every edge of the other (both directions); for the dense
    polylines this extension produces from flattened paths that is accurate
    enough to place a bridge.
    """
    best = (float("inf"), None, None)

    def scan(verts, edges_ring):
        nonlocal best
        m = len(edges_ring)
        for vx in verts:
            for k in range(m):
                cp, d2 = closest_point_on_segment(
                    vx, edges_ring[k], edges_ring[(k + 1) % m]
                )
                if d2 < best[0]:
                    best = (d2, vx, cp)

    scan(ring_a, ring_b)  # best = (d2, point_on_a, point_on_b)
    a_d2, a_pa, a_pb = best
    best = (float("inf"), None, None)
    scan(ring_b, ring_a)  # best = (d2, point_on_b, point_on_a)
    b_d2, b_pb, b_pa = best

    if a_d2 <= b_d2:
        return (math.sqrt(a_d2), a_pa, a_pb)
    return (math.sqrt(b_d2), b_pa, b_pb)


# --------------------------------------------------------------------------- #
# Arc-length helpers (even bridge spacing)
# --------------------------------------------------------------------------- #

def resample_closed(ring, count):
    """Return *count* points spaced evenly by arc length around *ring*."""
    n = len(ring)
    if n == 0 or count <= 0:
        return []
    cum = [0.0]
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    total = cum[-1]
    if total < EPS:
        return [ring[0]] * count
    out = []
    seg = 0
    for s in range(count):
        target = total * s / count
        while seg < n and cum[seg + 1] < target:
            seg += 1
        seg_len = cum[seg + 1] - cum[seg]
        t = 0.0 if seg_len < EPS else (target - cum[seg]) / seg_len
        x0, y0 = ring[seg % n]
        x1, y1 = ring[(seg + 1) % n]
        out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


# --------------------------------------------------------------------------- #
# Path "d" parsing + curve flattening
# --------------------------------------------------------------------------- #

class Subpath(object):
    """A flattened subpath: a list of points and whether it was closed (Z)."""

    __slots__ = ("points", "closed")

    def __init__(self, points, closed):
        self.points = points
        self.closed = closed


_NUM_CHARS = set("0123456789.eE+-")


def _tokenize(d):
    """Yield command letters and float numbers from an SVG path string."""
    i = 0
    length = len(d)
    while i < length:
        ch = d[i]
        if ch in " \t\r\n,":
            i += 1
            continue
        if ch.isalpha():
            yield ch
            i += 1
            continue
        # number: optional leading sign, one dot, one exponent with its own
        # optional sign (the "1.2.3" shorthand ends the token at the 2nd dot)
        j = i
        if d[j] in "+-":
            j += 1
        seen_dot = False
        seen_exp = False
        while j < length:
            cj = d[j]
            if cj.isdigit():
                j += 1
            elif cj == "." and not seen_dot and not seen_exp:
                seen_dot = True
                j += 1
            elif cj in "eE" and not seen_exp and j > i:
                seen_exp = True
                j += 1
                if j < length and d[j] in "+-":
                    j += 1
            else:
                break
        if j == i:  # not a number we recognise; skip one char defensively
            i += 1
            continue
        yield float(d[i:j])
        i = j


def _flatten_cubic(p0, p1, p2, p3, tol, out, depth=0):
    """Adaptively subdivide a cubic Bézier, appending interior+end points."""
    if depth > 24:
        out.append(p3)
        return
    # Flatness: max control-point deviation from the p0-p3 chord.
    ux = 3.0 * p1[0] - 2.0 * p0[0] - p3[0]
    uy = 3.0 * p1[1] - 2.0 * p0[1] - p3[1]
    vx = 3.0 * p2[0] - p0[0] - 2.0 * p3[0]
    vy = 3.0 * p2[1] - p0[1] - 2.0 * p3[1]
    flat = max(ux * ux, vx * vx) + max(uy * uy, vy * vy)
    if flat <= 16.0 * tol * tol:
        out.append(p3)
        return
    # de Casteljau split at t = 0.5
    p01 = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
    p12 = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    p23 = ((p2[0] + p3[0]) / 2.0, (p2[1] + p3[1]) / 2.0)
    p012 = ((p01[0] + p12[0]) / 2.0, (p01[1] + p12[1]) / 2.0)
    p123 = ((p12[0] + p23[0]) / 2.0, (p12[1] + p23[1]) / 2.0)
    mid = ((p012[0] + p123[0]) / 2.0, (p012[1] + p123[1]) / 2.0)
    _flatten_cubic(p0, p01, p012, mid, tol, out, depth + 1)
    _flatten_cubic(mid, p123, p23, p3, tol, out, depth + 1)


def _flatten_quadratic(p0, p1, p2, tol, out):
    # Elevate quadratic to cubic, then reuse the cubic flattener.
    c1 = (p0[0] + 2.0 / 3.0 * (p1[0] - p0[0]),
          p0[1] + 2.0 / 3.0 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2.0 / 3.0 * (p1[0] - p2[0]),
          p2[1] + 2.0 / 3.0 * (p1[1] - p2[1]))
    _flatten_cubic(p0, c1, c2, p2, tol, out)


def _arc_to_cubics(p0, rx, ry, phi_deg, large_arc, sweep, p1):
    """SVG elliptical arc -> list of cubic Bézier control quadruples."""
    if rx == 0 or ry == 0 or (abs(p0[0] - p1[0]) < EPS and
                              abs(p0[1] - p1[1]) < EPS):
        return [(p0, p0, p1, p1)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg % 360.0)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx = (p0[0] - p1[0]) / 2.0
    dy = (p0[1] - p1[1]) / 2.0
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den > EPS else 0.0
    if large_arc == sweep:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (p0[0] + p1[0]) / 2.0
    cy = sin_p * cxp + cos_p * cyp + (p0[1] + p1[1]) / 2.0

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        nrm = math.hypot(ux, uy) * math.hypot(vx, vy)
        a = math.acos(max(-1.0, min(1.0, dot / nrm))) if nrm > EPS else 0.0
        if ux * vy - uy * vx < 0:
            a = -a
        return a

    theta1 = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                   (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2.0 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2.0 * math.pi

    segs = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2.0))))
    out = []
    delta = dtheta / segs
    t = 4.0 / 3.0 * math.tan(delta / 4.0)
    a0 = theta1
    cur = p0
    for _ in range(segs):
        a1 = a0 + delta
        cos0, sin0 = math.cos(a0), math.sin(a0)
        cos1, sin1 = math.cos(a1), math.sin(a1)

        def pt(co_, si_):
            return (
                cx + rx * cos_p * co_ - ry * sin_p * si_,
                cy + rx * sin_p * co_ + ry * cos_p * si_,
            )

        e0 = pt(cos0, sin0)
        e1 = pt(cos1, sin1)
        q1 = (e0[0] - t * (rx * cos_p * sin0 + ry * sin_p * cos0),
              e0[1] - t * (rx * sin_p * sin0 - ry * cos_p * cos0))
        q2 = (e1[0] + t * (rx * cos_p * sin1 + ry * sin_p * cos1),
              e1[1] + t * (rx * sin_p * sin1 - ry * cos_p * cos1))
        out.append((cur, q1, q2, e1))
        cur = e1
        a0 = a1
    return out


def parse_path(d, tolerance=0.25):
    """Flatten an SVG path *d* string into a list of :class:`Subpath`.

    *tolerance* is the maximum chord deviation (in user units) allowed when
    sampling curves. Smaller = more points = more accurate.

    Supports the full path grammar: M m L l H h V v C c S s Q q T t A a Z z.
    """
    toks = list(_tokenize(d))
    i = 0
    subpaths = []
    pts = []
    start = (0.0, 0.0)
    cur = (0.0, 0.0)
    prev_cmd = ""
    prev_cubic_ctrl = None
    prev_quad_ctrl = None

    def num():
        nonlocal i
        v = toks[i]
        i += 1
        return v

    def flush(closed):
        if len(pts) >= 2:
            subpaths.append(Subpath(list(pts), closed))

    while i < len(toks):
        t = toks[i]
        if isinstance(t, str):
            cmd = t
            i += 1
        else:
            # Implicit repeat: M->L, m->l, others repeat themselves.
            cmd = prev_cmd
            if cmd == "M":
                cmd = "L"
            elif cmd == "m":
                cmd = "l"
        rel = cmd.islower()
        C = cmd.upper()

        if C == "M":
            if pts:
                flush(False)
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            start = cur
            pts = [cur]
        elif C == "Z":
            if pts:
                flush(True)
            pts = [start]
            cur = start
        elif C == "L":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.append(cur)
        elif C == "H":
            x = num()
            cur = (cur[0] + x, cur[1]) if rel else (x, cur[1])
            pts.append(cur)
        elif C == "V":
            y = num()
            cur = (cur[0], cur[1] + y) if rel else (cur[0], y)
            pts.append(cur)
        elif C in ("C", "S"):
            if C == "C":
                c1 = (num(), num())
                c2 = (num(), num())
            else:
                if prev_cmd.upper() in ("C", "S") and prev_cubic_ctrl:
                    c1 = (2 * cur[0] - prev_cubic_ctrl[0],
                          2 * cur[1] - prev_cubic_ctrl[1])
                else:
                    c1 = cur
                c2 = (num(), num())
            end = (num(), num())
            if rel:
                c1 = (cur[0] + c1[0], cur[1] + c1[1]) if C == "C" else c1
                c2 = (cur[0] + c2[0], cur[1] + c2[1])
                end = (cur[0] + end[0], cur[1] + end[1])
            buf = []
            _flatten_cubic(cur, c1, c2, end, tolerance, buf)
            pts.extend(buf)
            prev_cubic_ctrl = c2
            cur = end
        elif C in ("Q", "T"):
            if C == "Q":
                q = (num(), num())
                end = (num(), num())
                if rel:
                    q = (cur[0] + q[0], cur[1] + q[1])
                    end = (cur[0] + end[0], cur[1] + end[1])
            else:
                if prev_cmd.upper() in ("Q", "T") and prev_quad_ctrl:
                    q = (2 * cur[0] - prev_quad_ctrl[0],
                         2 * cur[1] - prev_quad_ctrl[1])
                else:
                    q = cur
                end = (num(), num())
                if rel:
                    end = (cur[0] + end[0], cur[1] + end[1])
            buf = []
            _flatten_quadratic(cur, q, end, tolerance, buf)
            pts.extend(buf)
            prev_quad_ctrl = q
            cur = end
        elif C == "A":
            rx, ry = num(), num()
            rot = num()
            large = num() != 0
            sweep = num() != 0
            ex, ey = num(), num()
            end = (cur[0] + ex, cur[1] + ey) if rel else (ex, ey)
            for (a, b, c, e) in _arc_to_cubics(
                cur, rx, ry, rot, large, sweep, end
            ):
                buf = []
                _flatten_cubic(a, b, c, e, tolerance, buf)
                pts.extend(buf)
            cur = end
        else:
            # Unknown command: stop parsing defensively.
            break

        if C not in ("C", "S"):
            prev_cubic_ctrl = None
        if C not in ("Q", "T"):
            prev_quad_ctrl = None
        prev_cmd = cmd

    if pts:
        flush(False)
    return subpaths


def flatten_superpath(csp, tolerance=0.25):
    """Flatten an inkex ``CubicSuperPath`` to ``list[list[(x, y)]]``.

    Each inkex subpath is ``[[ctrl_in, knot, ctrl_out], ...]`` with points as
    2-element sequences. Used at runtime so curve flattening is shared with,
    and behaves identically to, :func:`parse_path`.
    """
    out = []
    for sp in csp:
        if not sp:
            continue
        pts = [(float(sp[0][1][0]), float(sp[0][1][1]))]
        for k in range(len(sp) - 1):
            p0 = sp[k][1]
            c1 = sp[k][2]
            c2 = sp[k + 1][0]
            p3 = sp[k + 1][1]
            buf = []
            _flatten_cubic(
                (float(p0[0]), float(p0[1])),
                (float(c1[0]), float(c1[1])),
                (float(c2[0]), float(c2[1])),
                (float(p3[0]), float(p3[1])),
                tolerance,
                buf,
            )
            pts.extend(buf)
        out.append(pts)
    return out
