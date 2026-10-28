"""
Geometric, spatial, and coordinate translation utilities for rendered PDF bounding boxes.
"""

from typing import Any
from docling_core.types.doc import BoundingBox, CoordOrigin


def _get_item_label(item: Any) -> str:
    """
    Extracts the string representation of an item's label across Docling versions.
    """
    return item.label.value if hasattr(item.label, "value") else str(item.label)


def _to_topleft_dict(bbox: BoundingBox, page_h: float) -> dict[str, float]:
    """
    Converts a Docling BoundingBox to a top-left origin dictionary with keys 'l', 't', 'r', 'b'.
    """
    if bbox.coord_origin == CoordOrigin.BOTTOMLEFT:
        return {"l": bbox.l, "t": page_h - bbox.t, "r": bbox.r, "b": page_h - bbox.b}
    return {"l": bbox.l, "t": bbox.t, "r": bbox.r, "b": bbox.b}


def _compute_box_overlap(b1: dict[str, float], b2: dict[str, float]) -> tuple[float, float]:
    """
    Calculates the 2D spatial overlap (horizontal and vertical pixels) between two bounding boxes.
    Returns (x_overlap_px, y_overlap_px).
    """
    x_ov = max(0.0, min(b1["r"], b2["r"]) - max(b1["l"], b2["l"]))
    y_ov = max(0.0, min(b1["b"], b2["b"]) - max(b1["t"], b2["t"]))
    return x_ov, y_ov
