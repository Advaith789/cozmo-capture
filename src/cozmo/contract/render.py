"""Rendered floor plan as SVG.

Plain SVG with no dependencies, so the render path cannot fail for want of a
library on the machine it runs on. Dimensions are annotated with their
confidence interval, because a plan that shows a number without its interval
invites the reader to trust it more than the data supports.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..geometry.room import Room

PX_PER_M = 160.0
MARGIN = 90.0


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def room_svg(room: Room, title: str = "") -> str:
    poly = room.corners
    lo = poly.min(axis=0)
    span = poly.max(axis=0) - lo
    w = span[0] * PX_PER_M + 2 * MARGIN
    h = span[1] * PX_PER_M + 2 * MARGIN + 46

    def px(p: np.ndarray) -> tuple[float, float]:
        # SVG y grows downward; flip so the plan reads as a plan.
        return (MARGIN + (p[0] - lo[0]) * PX_PER_M,
                MARGIN + (span[1] - (p[1] - lo[1])) * PX_PER_M + 46)

    pts = [px(p) for p in poly]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
        f'height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">',
        '<style>'
        '.wall{fill:#f4f6f7;stroke:#1b2226;stroke-width:5;stroke-linejoin:round}'
        '.dim{stroke:#d14a16;stroke-width:1.2}'
        '.tick{stroke:#d14a16;stroke-width:1.2}'
        'text{font-family:ui-monospace,Menlo,monospace;fill:#1b2226}'
        '.d{font-size:12px;fill:#a03608}'
        '.ci{font-size:9.5px;fill:#6e7c84}'
        '.t{font-size:15px;font-weight:600}'
        '.s{font-size:10.5px;fill:#6e7c84}'
        '</style>',
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
        f'<text class="t" x="{MARGIN:.0f}" y="26">{_esc(title or room.name)}</text>',
        f'<text class="s" x="{MARGIN:.0f}" y="42">'
        f'floor area {room.floor_area.value:.2f} m² '
        f'(±{room.floor_area.half_width * 100:.0f} cm²) · '
        f'ceiling {room.ceiling_height.value:.3f} m '
        f'±{room.ceiling_height.half_width * 100:.1f} cm</text>',
        f'<polygon class="wall" points="{path}"/>',
    ]

    for i, m in enumerate(room.wall_lengths):
        a, b = np.array(pts[i]), np.array(pts[(i + 1) % len(pts)])
        mid = (a + b) / 2
        edge = b - a
        n = np.array([-edge[1], edge[0]])
        n = n / (np.linalg.norm(n) or 1)
        centre = np.mean(pts, axis=0)
        if n @ (mid - centre) < 0:      # push the label outside the room
            n = -n
        lab = mid + n * 30

        out.append(f'<line class="dim" x1="{a[0]:.1f}" y1="{a[1]:.1f}" '
                   f'x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                   f'transform="translate({n[0] * 16:.1f},{n[1] * 16:.1f})"/>')
        out.append(f'<text class="d" x="{lab[0]:.1f}" y="{lab[1]:.1f}" '
                   f'text-anchor="middle">{m.value:.3f} m</text>')
        out.append(f'<text class="ci" x="{lab[0]:.1f}" y="{lab[1] + 12:.1f}" '
                   f'text-anchor="middle">±{m.half_width * 100:.1f} cm</text>')

    out.append('</svg>')
    return "\n".join(out)


def write(room: Room, path: Path, title: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(room_svg(room, title))
    return path
