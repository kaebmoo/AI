"""
NT AI Assistant -- Telegram Chart Renderer
============================================
Renders query result data as PNG chart images for sending via Telegram.
Uses matplotlib with Thai font support.
"""

import io
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thai font configuration (resolved once at module level)
# ---------------------------------------------------------------------------
_THAI_FONT_FAMILY: Optional[str] = None
_FONT_INIT_DONE = False


def _init_thai_font() -> Optional[str]:
    """Attempt to find a Thai-capable font for matplotlib.

    Tries (in order):
    1. TH Sarabun New
    2. Tahoma (ships with many OS, supports Thai)
    3. None (fallback to matplotlib default -- Thai will be boxes)
    """
    global _THAI_FONT_FAMILY, _FONT_INIT_DONE
    if _FONT_INIT_DONE:
        return _THAI_FONT_FAMILY

    _FONT_INIT_DONE = True

    try:
        from matplotlib import font_manager

        preferred = ["TH Sarabun New", "TH SarabunPSK", "Tahoma", "Garuda", "Norasi"]
        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in preferred:
            if name in available:
                _THAI_FONT_FAMILY = name
                logger.info(f"Chart renderer: using Thai font '{name}'")
                return _THAI_FONT_FAMILY

        logger.warning("Chart renderer: no Thai font found; Thai text may not render correctly")
    except Exception as e:
        logger.warning(f"Chart renderer: font init error: {e}")

    return _THAI_FONT_FAMILY


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_chart_to_png(
    data: List[Dict],
    chart_type: str = "bar",
    title: str = "",
) -> bytes:
    """Render *data* as a PNG chart and return the raw bytes.

    Args:
        data: List of row dicts.  The first string-like column is used as
              labels (X axis) and the first numeric column as values (Y axis).
        chart_type: One of ``"bar"``, ``"line"``, ``"pie"``.
        title: Optional chart title.

    Returns:
        PNG image as ``bytes``.  Returns an empty-data placeholder image when
        *data* is empty or when no numeric column can be found.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # non-interactive backend
        import matplotlib.pyplot as plt
    except ImportError:
        logger.error("matplotlib is not installed; cannot render chart")
        return _empty_png("matplotlib not installed")

    # Font setup
    font_name = _init_thai_font()
    if font_name:
        plt.rcParams["font.family"] = font_name

    # Guard: empty data
    if not data:
        return _empty_png("ไม่มีข้อมูลสำหรับสร้างกราฟ")

    # Detect label and value columns
    label_col, value_col = _detect_columns(data)
    if not value_col:
        return _empty_png("ไม่พบคอลัมน์ตัวเลขสำหรับสร้างกราฟ")

    labels = [str(row.get(label_col, ""))[:30] for row in data[:20]]
    values = []
    for row in data[:20]:
        v = row.get(value_col, 0)
        try:
            values.append(float(v) if v is not None else 0)
        except (ValueError, TypeError):
            values.append(0)

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))

    chart_type = chart_type.lower().strip()
    if chart_type == "pie":
        # Filter out zero/negative for pie
        filtered = [(l, v) for l, v in zip(labels, values) if v > 0]
        if not filtered:
            plt.close(fig)
            return _empty_png("ไม่มีข้อมูลที่แสดงเป็นกราฟวงกลมได้")
        pie_labels, pie_values = zip(*filtered)
        ax.pie(pie_values, labels=pie_labels, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
    elif chart_type == "line":
        ax.plot(labels, values, marker="o", linewidth=2, color="#1976D2")
        ax.set_ylabel(value_col)
        plt.xticks(rotation=45, ha="right")
        ax.grid(axis="y", alpha=0.3)
    else:
        # Default: bar
        colors = _generate_colors(len(labels))
        ax.bar(labels, values, color=colors)
        ax.set_ylabel(value_col)
        plt.xticks(rotation=45, ha="right")
        ax.grid(axis="y", alpha=0.3)

    if title:
        ax.set_title(title, fontsize=14, pad=12)

    plt.tight_layout()

    # Export to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detect_columns(data: List[Dict]):
    """Identify the best label column and value column from the data.

    Returns ``(label_col, value_col)`` -- either may be ``None``.
    """
    if not data:
        return None, None

    first_row = data[0]
    label_col = None
    value_col = None

    for key, val in first_row.items():
        if value_col is None and _is_numeric(val):
            value_col = key
        elif label_col is None and not _is_numeric(val):
            label_col = key

    # If no label column found, use the first column regardless
    if label_col is None and first_row:
        label_col = list(first_row.keys())[0]

    return label_col, value_col


def _is_numeric(val) -> bool:
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def _generate_colors(n: int) -> List[str]:
    """Return a list of N distinct hex colours."""
    palette = [
        "#1976D2", "#388E3C", "#F57C00", "#D32F2F", "#7B1FA2",
        "#0097A7", "#AFB42B", "#5D4037", "#455A64", "#C2185B",
        "#00796B", "#FBC02D", "#512DA8", "#E64A19", "#0288D1",
        "#689F38", "#F44336", "#9C27B0", "#FF9800", "#607D8B",
    ]
    return [palette[i % len(palette)] for i in range(n)]


def _empty_png(message: str) -> bytes:
    """Generate a simple placeholder PNG with a centred text message."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        font_name = _init_thai_font()
        if font_name:
            plt.rcParams["font.family"] = font_name

        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14, color="#888")
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=100)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        # Absolute fallback: return a minimal 1x1 transparent PNG
        import struct
        import zlib

        def _minimal_png() -> bytes:
            sig = b"\x89PNG\r\n\x1a\n"
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
            raw = zlib.compress(b"\x00\xff\xff\xff")
            idat_crc = zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF
            idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
            iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
            iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
            return sig + ihdr + idat + iend

        return _minimal_png()
