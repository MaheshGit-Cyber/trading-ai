"""Deterministic candlestick chart renderer.

Two outputs from one drawing model:

* ``render_svg`` -- pure stdlib, no dependencies. This is the default.
* ``render_png`` -- uses Pillow when installed, for Telegram/WhatsApp delivery.

The drawing model is a list of primitives (line, rect, text, polyline,
polygon). SVG and PNG renderers consume the same list, so a chart cannot
look different between formats.

No model calls. No network. Given the same ``ChartSpec``, the output is
byte-identical (SVG) or pixel-identical (PNG).
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import math
import os

THEMES = {
    "dark": {
        "bg": "#0b1220",
        "panel": "#0f172a",
        "grid": "#1e293b",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "up": "#22c55e",
        "down": "#ef4444",
        "ma": ("#38bdf8", "#f59e0b", "#a78bfa", "#f472b6"),
        "entry": "#f59e0b",
        "stop": "#ef4444",
        "target": "#22c55e",
        "neutral": "#94a3b8",
        "axis": "#64748b",
    },
    "light": {
        "bg": "#ffffff",
        "panel": "#f8fafc",
        "grid": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#475569",
        "up": "#16a34a",
        "down": "#dc2626",
        "ma": ("#0284c7", "#d97706", "#7c3aed", "#db2777"),
        "entry": "#d97706",
        "stop": "#dc2626",
        "target": "#16a34a",
        "neutral": "#475569",
        "axis": "#64748b",
    },
}


@dataclass(frozen=True, slots=True)
class ChartBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if not self.date:
            raise ValueError("bar.date required")
        if self.high < self.low - 1e-9:
            raise ValueError("high must be >= low")
        if self.high < max(self.open, self.close) - 1e-9:
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close) + 1e-9:
            raise ValueError("low must be <= open and close")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("prices must be > 0")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")


@dataclass(frozen=True, slots=True)
class ChartLevel:
    price: float
    label: str
    color: str = "#f59e0b"
    style: str = "dashed"

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("level price must be > 0")
        if not self.label:
            raise ValueError("level label required")
        if self.style not in ("solid", "dashed", "dotted"):
            raise ValueError("style must be solid/dashed/dotted")


@dataclass(frozen=True, slots=True)
class ChartAnnotation:
    bar_index: int
    text: str
    direction: str = "neutral"
    color: str | None = None

    def __post_init__(self) -> None:
        if self.direction not in ("bullish", "bearish", "neutral"):
            raise ValueError("direction must be bullish/bearish/neutral")
        if not self.text:
            raise ValueError("annotation text required")


@dataclass(frozen=True, slots=True)
class ChartSpec:
    symbol: str
    bars: tuple[ChartBar, ...]
    timeframe: str = "daily"
    title: str = ""
    levels: tuple[ChartLevel, ...] = ()
    annotations: tuple[ChartAnnotation, ...] = ()
    show_ma: tuple[int, ...] = (20, 50, 200)
    show_volume: bool = True
    show_rsi: bool = True
    width: int = 1200
    height: int = 800
    theme: str = "dark"
    source: str = ""
    disclaimer: str = "Research only. Not investment advice."
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol required")
        if not self.bars:
            raise ValueError("at least one bar required")
        if self.width < 480 or self.height < 360:
            raise ValueError("canvas must be at least 480x360")
        if self.theme not in THEMES:
            raise ValueError(f"unknown theme {self.theme!r}")
        for period in self.show_ma:
            if period < 2:
                raise ValueError("MA periods must be >= 2")
        for ann in self.annotations:
            if not 0 <= ann.bar_index < len(self.bars):
                raise ValueError("annotation bar_index out of range")


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average. ``None`` until the window is full."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """Wilder RSI. ``None`` until the first average is available."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# Drawing primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Line:
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    width: float = 1.0
    dash: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class _Rect:
    x: float
    y: float
    w: float
    h: float
    fill: str | None
    stroke: str | None = None
    stroke_width: float = 0.0


@dataclass(frozen=True, slots=True)
class _Text:
    x: float
    y: float
    text: str
    color: str
    size: int
    anchor: str = "start"
    weight: str = "normal"


@dataclass(frozen=True, slots=True)
class _Polyline:
    points: tuple[tuple[float, float], ...]
    color: str
    width: float = 1.5


@dataclass(frozen=True, slots=True)
class _Polygon:
    points: tuple[tuple[float, float], ...]
    fill: str
    stroke: str
    stroke_width: float = 0.0


# ---------------------------------------------------------------------------
# Layout / scale helpers
# ---------------------------------------------------------------------------


def _theme(spec: ChartSpec) -> dict:
    return THEMES[spec.theme]


def _layout(spec: ChartSpec) -> dict:
    width, height = spec.width, spec.height
    left = 18.0
    right = width - 88.0
    top = 86.0
    bottom = height - 58.0
    plot_w = right - left
    plot_h = bottom - top

    has_vol = spec.show_volume and any(b.volume > 0 for b in spec.bars)
    has_rsi = spec.show_rsi and len(spec.bars) >= 15
    gap = 12.0

    if has_vol and has_rsi:
        price_h = plot_h * 0.60
        vol_h = plot_h * 0.15
        rsi_h = plot_h * 0.17
    elif has_vol:
        price_h = plot_h * 0.78
        vol_h = plot_h * 0.18
        rsi_h = 0.0
    elif has_rsi:
        price_h = plot_h * 0.78
        vol_h = 0.0
        rsi_h = plot_h * 0.18
    else:
        price_h = plot_h
        vol_h = 0.0
        rsi_h = 0.0

    price_top = top
    price_bottom = price_top + price_h
    vol_top = price_bottom + gap
    vol_bottom = vol_top + vol_h
    rsi_top = vol_bottom + gap
    rsi_bottom = rsi_top + rsi_h

    return {
        "left": left,
        "right": right,
        "top": top,
        "bottom": bottom,
        "plot_w": plot_w,
        "plot_h": plot_h,
        "n": len(spec.bars),
        "has_vol": has_vol,
        "has_rsi": has_rsi,
        "price_top": price_top,
        "price_bottom": price_bottom,
        "vol_top": vol_top,
        "vol_bottom": vol_bottom,
        "rsi_top": rsi_top,
        "rsi_bottom": rsi_bottom,
    }


def _price_scale(bars: tuple[ChartBar, ...]) -> tuple[float, float]:
    """Scale to the bars, with a 25% band for nearby trade levels.

    A level far outside the band is drawn as an edge marker instead of
    expanding the scale. One typo in ``--entry`` must not flatten the
    entire chart into a line at the bottom.
    """
    bar_lo = min(b.low for b in bars)
    bar_hi = max(b.high for b in bars)
    bar_range = max(bar_hi - bar_lo, bar_hi * 0.01, 1.0)
    band = bar_range * 0.25
    return bar_lo - band, bar_hi + band


def _y(value: float, lo: float, hi: float, top: float, bottom: float) -> float:
    if hi <= lo:
        return (top + bottom) / 2.0
    return bottom - (value - lo) / (hi - lo) * (bottom - top)


def _x(index: int, lay: dict) -> float:
    return lay["left"] + (index + 0.5) * lay["plot_w"] / lay["n"]


def _rsi_y(value: float, lay: dict) -> float:
    return lay["rsi_bottom"] - (value / 100.0) * (
        lay["rsi_bottom"] - lay["rsi_top"]
    )


def _tick_indices(n: int, count: int) -> list[int]:
    if n <= count:
        return list(range(n))
    return sorted({int(round(i * (n - 1) / (count - 1))) for i in range(count)})


def _short_date(value: str) -> str:
    return value[5:10] if len(value) >= 10 else value


def _price(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _volume(value: float) -> str:
    if value >= 1e7:
        return f"{value / 1e7:.2f}Cr"
    if value >= 1e5:
        return f"{value / 1e5:.2f}L"
    if value >= 1e3:
        return f"{value / 1e3:.1f}K"
    return f"{value:.0f}"


def _dash_for(style: str) -> tuple[float, float] | None:
    if style == "dashed":
        return (6.0, 4.0)
    if style == "dotted":
        return (2.0, 3.0)
    return None


# ---------------------------------------------------------------------------
# Build the primitive list
# ---------------------------------------------------------------------------


def _build(spec: ChartSpec) -> list[object]:
    theme = _theme(spec)
    bars = spec.bars
    lay = _layout(spec)
    lo, hi = _price_scale(bars)
    closes = [b.close for b in bars]
    prims: list[object] = []

    prims.append(_Rect(0, 0, spec.width, spec.height, theme["bg"]))

    title = spec.title or f"{spec.symbol} — {spec.timeframe.title()}"
    prims.append(_Text(lay["left"], 28, title, theme["text"], 20, "start", "bold"))

    first, last = bars[0], bars[-1]
    change = (last.close - first.close) / first.close * 100.0 if first.close else 0.0
    subtitle = (
        f"{first.date} → {last.date}  |  last {_price(last.close)}"
        f"  |  {change:+.2f}%"
    )
    if spec.source:
        subtitle += f"  |  {spec.source}"
    prims.append(_Text(lay["left"], 50, subtitle, theme["muted"], 11))

    # MA legend.
    lx = lay["left"]
    for k, period in enumerate(spec.show_ma):
        if period > len(bars):
            continue
        color = theme["ma"][k % len(theme["ma"])]
        prims.append(_Line(lx, 70, lx + 16, 70, color, 2))
        label = f"MA{period}"
        prims.append(_Text(lx + 20, 70, label, theme["muted"], 10))
        lx += 20 + len(label) * 6 + 16

    # Price grid + right axis.
    for k in range(5):
        value = lo + (hi - lo) * k / 4.0
        y = _y(value, lo, hi, lay["price_top"], lay["price_bottom"])
        prims.append(_Line(lay["left"], y, lay["right"], y, theme["grid"], 1,
                           (2.0, 4.0)))
        prims.append(_Text(lay["right"] + 6, y, _price(value),
                           theme["muted"], 10))

    # Vertical grid + date axis. Edge labels are anchored inward so they
    # are not clipped by the canvas.
    ticks = _tick_indices(len(bars), 6)
    for j, i in enumerate(ticks):
        x = _x(i, lay)
        prims.append(_Line(x, lay["price_top"], x, lay["bottom"],
                           theme["grid"], 1, (2.0, 4.0)))
        if j == 0:
            tx, anchor = lay["left"], "start"
        elif j == len(ticks) - 1:
            tx, anchor = lay["right"], "end"
        else:
            tx, anchor = x, "middle"
        prims.append(_Text(tx, lay["bottom"] + 16, _short_date(bars[i].date),
                           theme["muted"], 9, anchor))

    # Candles.
    step = lay["plot_w"] / len(bars)
    body_w = max(1.0, step * 0.62)
    for i, bar in enumerate(bars):
        x = _x(i, lay)
        color = theme["up"] if bar.close >= bar.open else theme["down"]
        y_high = _y(bar.high, lo, hi, lay["price_top"], lay["price_bottom"])
        y_low = _y(bar.low, lo, hi, lay["price_top"], lay["price_bottom"])
        prims.append(_Line(x, y_high, x, y_low, color, 1))
        y_open = _y(bar.open, lo, hi, lay["price_top"], lay["price_bottom"])
        y_close = _y(bar.close, lo, hi, lay["price_top"], lay["price_bottom"])
        top = min(y_open, y_close)
        height = max(1.0, abs(y_close - y_open))
        prims.append(_Rect(x - body_w / 2.0, top, body_w, height, color))

    # Moving averages.
    for k, period in enumerate(spec.show_ma):
        if period > len(bars):
            continue
        values = sma(closes, period)
        points = tuple(
            (_x(i, lay), _y(v, lo, hi, lay["price_top"], lay["price_bottom"]))
            for i, v in enumerate(values)
            if v is not None
        )
        if len(points) >= 2:
            prims.append(_Polyline(points, theme["ma"][k % len(theme["ma"])],
                                   1.6))

    # Entry / stop / target levels. Off-chart levels become one combined
    # edge marker instead of expanding the price scale.
    above: list[str] = []
    below: list[str] = []
    for level in spec.levels:
        if level.price > hi:
            above.append(f"{level.label} {_price(level.price)}")
            continue
        if level.price < lo:
            below.append(f"{level.label} {_price(level.price)}")
            continue
        y = _y(level.price, lo, hi, lay["price_top"], lay["price_bottom"])
        prims.append(_Line(lay["left"], y, lay["right"], y, level.color, 1.4,
                           _dash_for(level.style)))
        prims.append(_Text(
            lay["right"] - 4, y - 4,
            f"{level.label} {_price(level.price)}",
            level.color, 10, "end", "bold",
        ))
    if above:
        prims.append(_Text(
            lay["right"] - 4, lay["price_top"] + 10,
            "↑ " + " · ".join(above), theme["muted"], 9, "end", "bold",
        ))
    if below:
        prims.append(_Text(
            lay["right"] - 4, lay["price_bottom"] - 10,
            "↓ " + " · ".join(below), theme["muted"], 9, "end", "bold",
        ))

    # Pattern annotations.
    for ann in spec.annotations:
        i = max(0, min(len(bars) - 1, ann.bar_index))
        bar = bars[i]
        x = _x(i, lay)
        color = ann.color or {
            "bullish": theme["up"],
            "bearish": theme["down"],
        }.get(ann.direction, theme["neutral"])
        if ann.direction == "bullish":
            y0 = _y(bar.low, lo, hi, lay["price_top"], lay["price_bottom"]) + 12
            points = ((x, y0), (x - 6, y0 + 10), (x + 6, y0 + 10))
            text_y = y0 + 22
        elif ann.direction == "bearish":
            y0 = _y(bar.high, lo, hi, lay["price_top"], lay["price_bottom"]) - 12
            points = ((x, y0), (x - 6, y0 - 10), (x + 6, y0 - 10))
            text_y = y0 - 22
        else:
            y0 = _y(bar.high, lo, hi, lay["price_top"], lay["price_bottom"]) - 12
            points = ((x, y0 - 5), (x + 5, y0), (x, y0 + 5), (x - 5, y0))
            text_y = y0 - 18
        prims.append(_Polygon(points, color, color, 0.0))
        label = ann.text[:28]
        text_w = max(28.0, len(label) * 5.8 + 8.0)
        text_x = min(
            max(x, lay["left"] + text_w / 2.0 + 2.0),
            lay["right"] - text_w / 2.0 - 2.0,
        )
        text_y = min(
            max(text_y, lay["price_top"] + 10.0),
            lay["price_bottom"] - 10.0,
        )
        prims.append(_Rect(text_x - text_w / 2.0, text_y - 8, text_w, 16,
                           theme["panel"], color, 0.8))
        prims.append(_Text(text_x, text_y, label, color, 9, "middle"))

    # Volume panel.
    if lay["has_vol"]:
        max_vol = max((b.volume for b in bars), default=0.0)
        prims.append(_Text(lay["left"] + 4, lay["vol_top"] + 10, "Volume",
                           theme["muted"], 9))
        if max_vol > 0:
            usable = lay["vol_bottom"] - lay["vol_top"] - 16
            for i, bar in enumerate(bars):
                if bar.volume <= 0:
                    continue
                x = _x(i, lay)
                height = bar.volume / max_vol * usable
                color = theme["up"] if bar.close >= bar.open else theme["down"]
                prims.append(_Rect(x - body_w / 2.0, lay["vol_bottom"] - height,
                                   body_w, height, color))
            prims.append(_Text(lay["right"] + 6, lay["vol_top"] + 10,
                               _volume(max_vol), theme["muted"], 9))

    # RSI panel.
    if lay["has_rsi"]:
        values = rsi(closes, 14)
        prims.append(_Text(lay["left"] + 4, lay["rsi_top"] + 10, "RSI(14)",
                           theme["muted"], 9))
        for level in (30, 50, 70):
            y = _rsi_y(level, lay)
            dash = (4.0, 4.0) if level != 50 else (2.0, 4.0)
            prims.append(_Line(lay["left"], y, lay["right"], y, theme["grid"],
                               1, dash))
            prims.append(_Text(lay["right"] + 6, y, str(level),
                               theme["muted"], 9))
        points = tuple(
            (_x(i, lay), _rsi_y(v, lay))
            for i, v in enumerate(values)
            if v is not None
        )
        if len(points) >= 2:
            prims.append(_Polyline(points, theme["ma"][0], 1.4))

    # Footer.
    if spec.source:
        prims.append(_Text(lay["left"], spec.height - 28, spec.source,
                           theme["muted"], 9))
    prims.append(_Text(lay["left"], spec.height - 12, spec.disclaimer,
                       theme["muted"], 9))
    if spec.generated_at:
        prims.append(_Text(lay["right"], spec.height - 12, spec.generated_at,
                           theme["muted"], 9, "end"))

    return prims


# ---------------------------------------------------------------------------
# SVG renderer
# ---------------------------------------------------------------------------


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _svg(prims: list[object], width: int, height: int) -> str:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="DejaVu Sans, Arial, sans-serif" role="img">'
    ]
    for p in prims:
        if isinstance(p, _Line):
            dash = ""
            if p.dash:
                dash = f' stroke-dasharray="{p.dash[0]} {p.dash[1]}"'
            parts.append(
                f'<line x1="{p.x1:.2f}" y1="{p.y1:.2f}" x2="{p.x2:.2f}" '
                f'y2="{p.y2:.2f}" stroke="{p.color}" '
                f'stroke-width="{p.width:.2f}"{dash}/>'
            )
        elif isinstance(p, _Rect):
            fill = p.fill if p.fill else "none"
            stroke = ""
            if p.stroke:
                stroke = (f' stroke="{p.stroke}" '
                          f'stroke-width="{p.stroke_width:.2f}"')
            parts.append(
                f'<rect x="{p.x:.2f}" y="{p.y:.2f}" width="{p.w:.2f}" '
                f'height="{p.h:.2f}" fill="{fill}"{stroke}/>'
            )
        elif isinstance(p, _Text):
            weight = ' font-weight="600"' if p.weight == "bold" else ""
            parts.append(
                f'<text x="{p.x:.2f}" y="{p.y:.2f}" fill="{p.color}" '
                f'font-size="{p.size}" text-anchor="{p.anchor}" '
                f'dominant-baseline="middle"{weight}>{_esc(p.text)}</text>'
            )
        elif isinstance(p, _Polyline):
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in p.points)
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="{p.color}" '
                f'stroke-width="{p.width:.2f}" stroke-linejoin="round" '
                f'stroke-linecap="round"/>'
            )
        elif isinstance(p, _Polygon):
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in p.points)
            parts.append(
                f'<polygon points="{points}" fill="{p.fill}" '
                f'stroke="{p.stroke}" stroke-width="{p.stroke_width:.2f}"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_svg(spec: ChartSpec, path: str | None = None) -> str:
    """Return SVG text, or write it to ``path`` and return the path."""
    text = _svg(_build(spec), spec.width, spec.height)
    if path is None:
        return text
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# PNG renderer (Pillow optional)
# ---------------------------------------------------------------------------


_FONT_CANDIDATES = {
    False: (
        "/system/fonts/Roboto-Regular.ttf",
        "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
    True: (
        "/system/fonts/Roboto-Bold.ttf",
        "/system/fonts/Roboto-Regular.ttf",
        "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
    ),
}

_FONT_CACHE: dict[tuple[int, bool], object] = {}


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = None
    for path in _FONT_CANDIDATES[bold]:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
    if font is None:
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _dashed_line(draw, x1: float, y1: float, x2: float, y2: float,
                 fill: str, width: int, dash: tuple[float, float]) -> None:
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 0:
        return
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    pos = 0.0
    on = True
    while pos < length:
        seg = dash[0] if on else dash[1]
        end = min(pos + seg, length)
        if on:
            draw.line(
                [(x1 + ux * pos, y1 + uy * pos),
                 (x1 + ux * end, y1 + uy * end)],
                fill=fill, width=width,
            )
        pos = end
        on = not on


def render_png(spec: ChartSpec, path: str) -> str:
    """Render PNG with Pillow. Raises ``RuntimeError`` if Pillow is absent."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "Pillow is required for PNG output; install pillow or use .svg"
        ) from exc

    prims = _build(spec)
    image = Image.new("RGB", (spec.width, spec.height), THEMES[spec.theme]["bg"])
    draw = ImageDraw.Draw(image)

    for p in prims:
        if isinstance(p, _Line):
            if p.dash:
                _dashed_line(draw, p.x1, p.y1, p.x2, p.y2, p.color,
                             max(1, int(round(p.width))), p.dash)
            else:
                draw.line([(p.x1, p.y1), (p.x2, p.y2)], fill=p.color,
                          width=max(1, int(round(p.width))))
        elif isinstance(p, _Rect):
            box = [p.x, p.y, p.x + p.w, p.y + p.h]
            outline = p.stroke if p.stroke else None
            width = max(1, int(round(p.stroke_width))) if outline else 0
            draw.rectangle(box, fill=p.fill, outline=outline, width=width)
        elif isinstance(p, _Text):
            font = _font(p.size, p.weight == "bold")
            anchor = {"start": "lm", "middle": "mm", "end": "rm"}.get(
                p.anchor, "lm"
            )
            draw.text((p.x, p.y), p.text, font=font, fill=p.color,
                      anchor=anchor)
        elif isinstance(p, _Polyline):
            points = [(x, y) for x, y in p.points]
            if len(points) >= 2:
                draw.line(points, fill=p.color,
                          width=max(1, int(round(p.width))), joint="curve")
        elif isinstance(p, _Polygon):
            points = [(x, y) for x, y in p.points]
            if len(points) >= 3:
                draw.polygon(points, fill=p.fill, outline=p.stroke)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    image.save(tmp, "PNG")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def render(spec: ChartSpec, path: str) -> str:
    """Write ``spec`` to ``path``; format follows the extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".svg":
        return render_svg(spec, path)
    if ext == ".png":
        return render_png(spec, path)
    raise ValueError("output path must end in .svg or .png")
