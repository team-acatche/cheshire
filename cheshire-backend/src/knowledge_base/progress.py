from __future__ import annotations

import math
import threading
import time
from contextvars import ContextVar
from typing import Any, Optional

STAGES: list[tuple[str, str]] = [
    ("parsing", "Reading the PDF"),
    ("auditing", "Auditing sections"),
    ("dedup", "Merging duplicates"),
    ("global", "Document-wide checks"),
    ("finalizing", "Saving findings"),
]

# (start %, end %) of the overall bar that each stage owns
STAGE_RANGES: dict[str, tuple[float, float]] = {
    "queued": (0, 0),
    "parsing": (0, 12),
    "auditing": (12, 72),
    "dedup": (72, 86),
    "global": (86, 96),
    "finalizing": (96, 99),
}
# Time constants (s) for stages with no measurable sub-progress. The bar eases
# toward the end of its range instead of freezing.
CREEP_TAU = {"parsing": 45.0, "dedup": 30.0, "global": 30.0, "finalizing": 5.0}
MAX_EVENTS = 200
MAX_ACTIVE_PAGES = 8


class ProgressTracker:
    """Thread-safe progress state for one evaluation run."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.started_at = time.time()
        self.stage = "queued"
        self.stage_started_at = self.started_at
        self.message = "Waiting for a worker…"
        self.completed = 0
        self.total = 0
        self.heading: Optional[str] = None
        self.page_count = 0
        self.active_pages: list[int] = []
        self.scanned_pages: set[int] = set()
        self.counts = {"major": 0, "minor": 0, "observation": 0}
        self.terminal: Optional[str] = None
        self._chunk_t0: Optional[float] = None
        self._chunk_times: list[float] = []
        self._events: list[dict[str, Any]] = []
        self._seq = 0
        self._percent = 0.0

    # ── writers (called from the worker thread) ───────────────────────────
    def log(self, kind: str, message: str, **data: Any) -> None:
        with self._lock:
            self._seq += 1
            self._events.append({
                "seq": self._seq,
                "t": round(time.time() - self.started_at, 1),
                "kind": kind,
                "message": message,
                **data,
            })
            del self._events[:-MAX_EVENTS]

    def set_stage(self, stage: str, message: str) -> None:
        with self._lock:
            self.stage = stage
            self.stage_started_at = time.time()
            self.message = message
            if stage != "auditing":
                self.active_pages = []
                self.heading = None
            self.log("stage", message)

    def set_document(self, *, page_count: int, sections: int, figures: int) -> None:
        with self._lock:
            self.page_count = page_count
            self.log("info", f"Found {page_count} pages, {sections} sections and {figures} figures")

    def begin_chunk(self, index: int, total: int, heading: str, page_range: tuple[int, int], figures: int) -> None:
        with self._lock:
            lo, hi = page_range
            self.total = total
            self.completed = index
            self.heading = heading
            self.active_pages = list(range(lo, min(hi, lo + MAX_ACTIVE_PAGES - 1) + 1)) if lo > 0 else []
            self._chunk_t0 = time.time()
            pages = f"p{lo}" if lo == hi else f"p{lo}–{hi}"
            extra = f" · {figures} figure{'s' if figures != 1 else ''}" if figures else ""
            self.message = f"Reading “{heading}”"
            self.log("section", f"Reading “{heading}” ({pages}){extra}")

    def end_chunk(self, page_range: tuple[int, int], findings: list[Any]) -> None:
        with self._lock:
            if self._chunk_t0 is not None:
                self._chunk_times.append(time.time() - self._chunk_t0)
                self._chunk_t0 = None
            self.completed += 1
            lo, hi = page_range
            if lo > 0:
                self.scanned_pages.update(range(lo, hi + 1))
            for f in findings:
                sev = getattr(f, "severity", None) or "observation"
                if sev not in self.counts:
                    sev = "observation"
                self.counts[sev] += 1
                text = getattr(f, "title", None) or getattr(f, "finding", "") or "Finding"
                self.log("finding", text if len(text) <= 90 else text[:87] + "…", severity=sev)

    def finish(self, status: str) -> None:
        with self._lock:
            self.terminal = status
            self.active_pages = []
            if status == "done":
                self._percent = 100.0

    # ── reader ────────────────────────────────────────────────────────────
    def _percent_now(self, now: float) -> float:
        if self.terminal == "done":
            return 100.0
        lo, hi = STAGE_RANGES.get(self.stage, (0, 0))
        if self.stage == "auditing" and self.total:
            creep = 0.0
            if self._chunk_t0 is not None and self._chunk_times:
                avg = sum(self._chunk_times[-5:]) / len(self._chunk_times[-5:])
                creep = min(0.9, (now - self._chunk_t0) / max(avg, 1.0))
            frac = min(1.0, (self.completed + creep) / self.total)
        else:
            tau = CREEP_TAU.get(self.stage)
            frac = 1 - math.exp(-(now - self.stage_started_at) / tau) if tau else 0.0
        self._percent = max(self._percent, lo + (hi - lo) * frac)  # never goes backwards
        return self._percent

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            keys = [k for k, _ in STAGES]
            eta: Optional[float] = None
            if self.stage == "auditing" and self._chunk_times and self.total:
                avg = sum(self._chunk_times[-5:]) / len(self._chunk_times[-5:])
                in_chunk = (now - self._chunk_t0) if self._chunk_t0 else 0.0
                eta = max(0.0, avg * (self.total - self.completed) - in_chunk)
            return {
                "stage": self.stage,
                "stage_index": keys.index(self.stage) if self.stage in keys else -1,
                "stages": [{"key": k, "label": l} for k, l in STAGES],
                "message": self.message,
                "percent": round(self._percent_now(now), 1),
                "completed": self.completed,
                "total": self.total,
                "heading": self.heading,
                "page_count": self.page_count,
                "active_pages": list(self.active_pages),
                "scanned_pages": sorted(self.scanned_pages),
                "counts": dict(self.counts),
                "eta_seconds": round(eta) if eta is not None else None,
                "elapsed_seconds": round(now - self.started_at),
                "terminal": self.terminal,
                "events": [e for e in self._events if e["seq"] > since],
                "last_seq": self._seq,
            }


current_progress: ContextVar[Optional[ProgressTracker]] = ContextVar("current_progress", default=None)


def get_progress() -> ProgressTracker:
    """The active tracker, or a throwaway one so callers never need `if`s (tests, scripts)."""
    return current_progress.get() or ProgressTracker()