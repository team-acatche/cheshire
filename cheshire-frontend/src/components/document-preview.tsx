import { useState, useRef, useCallback, useEffect } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import {
  useFloating,
  offset,
  flip,
  shift,
  autoUpdate,
  FloatingPortal,
} from "@floating-ui/react";
import {
  FileText,
  ExternalLink,
  ChevronRight,
  ChevronLeft,
  Search,
  X,
  ChevronUp,
  ChevronDown,
  Layers,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// ─── pdfjs worker ────────────────────────────────────────────────────────────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

// ─── Types ───────────────────────────────────────────────────────────────────
interface PageMeta {
  renderedWidth: number;
  renderedHeight: number;
  originalWidth: number;
  originalHeight: number;
}

interface ActiveGroup {
  findings: VulnerabilityFinding[];
  anchorEl: HTMLElement;
  bboxKey: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function makeBboxKey(f: VulnerabilityFinding) {
  return `${f.page_no}|${f.bbox.l}|${f.bbox.t}|${f.bbox.r}|${f.bbox.b}`;
}

function groupByBbox(findings: VulnerabilityFinding[], pageNumber: number) {
  const map = new Map<string, VulnerabilityFinding[]>();

  for (const f of findings) {
    if (f.page_no !== pageNumber) continue;
    const key = makeBboxKey(f);
    const group = map.get(key) ?? [];
    group.push(f);
    map.set(key, group);
  }

  return map;
}

// ─── Coordinate transform ────────────────────────────────────────────────────
function pdfToPixels(
  bbox: VulnerabilityFinding["bbox"],
  pageHeightPt: number,
  scale: number
) {
  return {
    left: bbox.l * scale,
    top: (pageHeightPt - bbox.t) * scale,
    width: (bbox.r - bbox.l) * scale,
    height: (bbox.t - bbox.b) * scale,
  };
}

// ─── SearchBar ───────────────────────────────────────────────────────────────
interface SearchBarProps {
  query: string;
  matchCount: number;
  currentMatch: number;
  onQueryChange: (q: string) => void;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function SearchBar({
  query,
  matchCount,
  currentMatch,
  onQueryChange,
  onNext,
  onPrev,
  onClose,
  inputRef,
}: SearchBarProps) {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-border bg-background shadow-sm">
      <Search className="size-3.5 text-muted-foreground shrink-0" />
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.shiftKey ? onPrev() : onNext();
          }
          if (e.key === "Escape") {
            onClose();
          }
        }}
        placeholder="Search in document…"
        className="flex-1 text-xs bg-transparent outline-none placeholder:text-muted-foreground"
      />

      {query && (
        <span className="text-[11px] text-muted-foreground shrink-0 tabular-nums">
          {matchCount === 0 ? "No results" : `${currentMatch + 1} / ${matchCount}`}
        </span>
      )}

      <button
        onClick={onPrev}
        disabled={matchCount === 0}
        className="p-0.5 rounded hover:bg-muted disabled:opacity-30"
        title="Previous (Shift+Enter)"
      >
        <ChevronUp className="size-3.5" />
      </button>

      <button
        onClick={onNext}
        disabled={matchCount === 0}
        className="p-0.5 rounded hover:bg-muted disabled:opacity-30"
        title="Next (Enter)"
      >
        <ChevronDown className="size-3.5" />
      </button>

      <button
        onClick={onClose}
        className="p-0.5 rounded hover:bg-muted"
        title="Close (Esc)"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

// ─── Search highlight helpers ────────────────────────────────────────────────
const injectedMarks: Set<HTMLElement> = new Set();

function getTextLayer(pageEl: HTMLElement): HTMLElement | null {
  return (
    pageEl.querySelector(".react-pdf__Page__textLayer") ??
    pageEl.querySelector(".react-pdf__Page__textContent")
  );
}

function clearAllMarks() {
  injectedMarks.forEach((mark) => {
    const parent = mark.parentNode;
    if (parent) {
      parent.replaceChild(document.createTextNode(mark.textContent ?? ""), mark);
      parent.normalize();
    }
  });
  injectedMarks.clear();
}

function applyPageHighlights(pageEl: HTMLElement, query: string): number {
  const textLayer = getTextLayer(pageEl);
  if (!textLayer || !query.trim()) return 0;

  const lowerQuery = query.toLowerCase();
  let count = 0;

  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let node: Text | null;

  while ((node = walker.nextNode() as Text | null)) {
    textNodes.push(node);
  }

  textNodes.forEach((textNode) => {
    const text = textNode.textContent ?? "";
    const lowerText = text.toLowerCase();
    const idx = lowerText.indexOf(lowerQuery);

    if (idx === -1) return;

    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + query.length);
    const after = text.slice(idx + query.length);

    const mark = document.createElement("mark");
    mark.textContent = match;
    mark.setAttribute("data-pdf-search", "true");
    mark.style.cssText =
      "background:rgba(59,130,246,0.35);outline:1px solid rgba(59,130,246,0.55);border-radius:2px;color:inherit;";

    injectedMarks.add(mark);

    const parent = textNode.parentNode;
    if (!parent) return;

    if (before) parent.insertBefore(document.createTextNode(before), textNode);
    parent.insertBefore(mark, textNode);
    if (after) parent.insertBefore(document.createTextNode(after), textNode);
    parent.removeChild(textNode);

    count++;
  });

  return count;
}

function markCurrentPageMatch(pageEl: HTMLElement, isCurrent: boolean) {
  const textLayer = getTextLayer(pageEl);
  textLayer?.querySelectorAll("[data-pdf-search]").forEach((el) => {
    const element = el as HTMLElement;

    if (isCurrent) {
      element.style.background = "rgba(234,179,8,0.55)";
      element.style.outline = "2px solid rgba(234,179,8,0.9)";
    } else {
      element.style.background = "rgba(59,130,246,0.35)";
      element.style.outline = "1px solid rgba(59,130,246,0.55)";
    }
  });
}

// ─── FindingOverlay ──────────────────────────────────────────────────────────
interface FindingOverlayProps {
  bboxKey: string;
  findings: VulnerabilityFinding[];
  scale: number;
  pageHeightPt: number;
  isActive: boolean;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
}

function FindingOverlay({
  bboxKey,
  findings,
  scale,
  pageHeightPt,
  isActive,
  onClick,
}: FindingOverlayProps) {
  const rect = pdfToPixels(findings[0].bbox, pageHeightPt, scale);
  const hasMultiple = findings.length > 1;

  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        onClick(findings, bboxKey, e.currentTarget);
      }}
      style={{
        position: "absolute",
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        pointerEvents: "all",
        cursor: "pointer",
        borderRadius: 3,
        background: isActive
          ? "rgba(0, 51, 178, 0.25)"
          : "rgba(0, 51, 178, 0.12)",
        borderBottom: isActive
          ? "2.5px solid rgba(0, 51, 178, 0.9)"
          : "2px solid rgba(0, 51, 178, 0.55)",
        boxShadow: isActive
          ? "0 0 0 1.5px rgba(0, 51, 178, 0.35)"
          : "none",
        transition: "all 150ms ease",
        zIndex: 20,
      }}
    >
      {hasMultiple && (
        <div
          style={{
            position: "absolute",
            top: -8,
            right: -8,
            background: isActive ? "rgb(0, 51, 178)" : "rgb(0, 82, 224)",
            color: "white",
            borderRadius: "9999px",
            fontSize: 10,
            fontWeight: 700,
            minWidth: 18,
            height: 18,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 4px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
            pointerEvents: "none",
            transition: "all 150ms ease",
          }}
        >
          {findings.length}
        </div>
      )}
    </div>
  );
}

// ─── FindingPopover ──────────────────────────────────────────────────────────
interface FindingPopoverProps {
  findings: VulnerabilityFinding[];
  anchorEl: HTMLElement;
  onClose: () => void;
}

function FindingPopover({ findings, anchorEl, onClose }: FindingPopoverProps) {
  const [page, setPage] = useState(0);
  const finding = findings[page];
  const total = findings.length;

  const { refs, floatingStyles } = useFloating({
    placement: "bottom-start",
    strategy: "fixed",
    middleware: [
      offset(10),
      flip({
        padding: 12,
        fallbackPlacements: ["top-start", "right-start", "left-start"],
      }),
      shift({ padding: 12 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(anchorEl);
    setPage(0); // reset pagination whenever a new highlight is clicked
  }, [anchorEl, refs, findings]);



  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    const handlePointerDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      const floating = refs.floating.current;

      if (
        floating &&
        target &&
        !floating.contains(target) &&
        !anchorEl.contains(target)
      ) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousedown", handlePointerDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [anchorEl, onClose, refs.floating]);

  return (
    <FloatingPortal>
      <div
        ref={refs.setFloating}
        style={{ ...floatingStyles, zIndex: 9999 }}
        className="
          w-80 rounded-xl border border-blue-200/60 bg-white shadow-xl
          ring-1 ring-black/5 overflow-hidden
          dark:bg-zinc-900 dark:border-blue-400/20
          origin-top-left
          animate-in fade-in-0 zoom-in-95 slide-in-from-top-2
          duration-300
        "
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-blue-50 dark:bg-blue-950/40 px-4 py-3 border-b border-blue-100/80 dark:border-blue-400/15">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug flex-1">
              {finding.title}
            </p>

            <Badge
              variant="outline"
              className="shrink-0 text-[10px] border-blue-300 text-blue-700 dark:text-blue-400 dark:border-blue-600"
            >
              pg. {finding.page_no}
            </Badge>
          </div>

          {total > 1 && (
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-blue-100/60 dark:border-blue-400/10">
              <div className="flex items-center gap-1 text-[11px] text-blue-700 dark:text-blue-400 font-medium">
                <Layers className="size-3" />
                <span>
                  {page + 1} of {total} findings
                </span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-0.5 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Previous finding"
                >
                  <ChevronLeft className="size-3.5 text-blue-700 dark:text-blue-400" />
                </button>

                <div className="flex gap-0.5">
                  {findings.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setPage(i)}
                      className={`rounded-full transition-all ${
                        i === page
                          ? "w-3 h-1.5 bg-blue-500"
                          : "w-1.5 h-1.5 bg-blue-300 hover:bg-blue-400"
                      }`}
                      aria-label={`Go to finding ${i + 1}`}
                    />
                  ))}
                </div>

                <button
                  onClick={() => setPage((p) => Math.min(total - 1, p + 1))}
                  disabled={page === total - 1}
                  className="p-0.5 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Next finding"
                >
                  <ChevronRight className="size-3.5 text-blue-700 dark:text-blue-400" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-4 py-3 space-y-3 max-h-72 overflow-y-auto">
          <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
            {finding.description}
          </p>

          {finding.recommendations.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1.5">
                Recommendations
              </p>
              <ul className="space-y-1.5">
                {finding.recommendations.map((rec, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-xs text-zinc-700 dark:text-zinc-300 leading-snug"
                  >
                    <ChevronRight className="size-3 mt-0.5 shrink-0 text-blue-500" />
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {finding.web_references.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1.5">
                References
              </p>
              <ul className="space-y-1">
                {finding.web_references.map((url, i) => (
                  <li key={i}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline truncate"
                    >
                      <ExternalLink className="size-3 shrink-0" />
                      <span className="truncate">{url}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </FloatingPortal>
  );
}

// ─── HighlightLayer ──────────────────────────────────────────────────────────
interface HighlightLayerProps {
  pageNumber: number;
  pageMeta: PageMeta;
  findings: VulnerabilityFinding[];
  activeBboxKey: string | null;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
}

function HighlightLayer({
  pageNumber,
  pageMeta,
  findings,
  activeBboxKey,
  onClick,
}: HighlightLayerProps) {
  const scale = pageMeta.renderedWidth / pageMeta.originalWidth;
  const groups = groupByBbox(findings, pageNumber);

  if (groups.size === 0) return null;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        zIndex: 20,
      }}
    >
      {Array.from(groups.entries()).map(([bboxKey, group]) => (
        <FindingOverlay
          key={bboxKey}
          bboxKey={bboxKey}
          findings={group}
          scale={scale}
          pageHeightPt={pageMeta.originalHeight}
          isActive={activeBboxKey === bboxKey}
          onClick={onClick}
        />
      ))}
    </div>
  );
}

// ─── DocumentPreview ─────────────────────────────────────────────────────────
interface DocumentPreviewProps {
  src: File | string;
  findings: VulnerabilityFinding[];
  fileName?: string;
}

export function DocumentPreview({ src, findings, fileName }: DocumentPreviewProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageMetaMap, setPageMetaMap] = useState<Record<number, PageMeta>>({});
  const [active, setActive] = useState<ActiveGroup | null>(null);
  const [containerWidth, setContainerWidth] = useState(800);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");

  // Search state
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchPages, setMatchPages] = useState<number[]>([]);
  const [matchIdx, setMatchIdx] = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const pageEls = useRef<Record<number, HTMLDivElement | null>>({});

  const isUrl = typeof src === "string";
  const displayFileName = fileName ?? (isUrl ? "document.pdf" : src.name);
  const isPdf = isUrl ? true : src.type === "application/pdf";
  const pdfSource: File | string = src;

  const measuredRef = useCallback((node: HTMLDivElement | null) => {
    if (!node) return;

    setContainerWidth(node.getBoundingClientRect().width);

    const ro = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });

    ro.observe(node);

    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }

      if (e.key === "Escape") {
        setSearchOpen(false);
        setSearchQuery("");
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visiblePages = entries
          .filter((entry) => entry.isIntersecting)
          .map((entry) => ({
            page: Number((entry.target as HTMLElement).dataset.pageNumber),
            ratio: entry.intersectionRatio,
          }))
          .sort((a, b) => b.ratio - a.ratio);

        if (visiblePages.length > 0) {
          setCurrentPage(visiblePages[0].page);
        }
      },
      {
        root: null,
        threshold: [0.25, 0.5, 0.75],
      }
    );

    Object.entries(pageEls.current).forEach(([pageNum, el]) => {
      if (el) {
        el.dataset.pageNumber = pageNum;
        observer.observe(el);
      }
    });

    return () => observer.disconnect();
  }, [numPages]);

  const scrollToPage = useCallback((pageNum: number) => {
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (el) {
        markCurrentPageMatch(el, Number(num) === pageNum);
      }
    });

    pageEls.current[pageNum]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, []);

  const scrollToPageNumber = useCallback((pageNum: number) => {
    const el = pageEls.current[pageNum];
    if (!el) return;

    setCurrentPage(pageNum);
    el.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, []);

  const goToNextPage = useCallback(() => {
    if (currentPage >= numPages) return;
    scrollToPageNumber(currentPage + 1);
  }, [currentPage, numPages, scrollToPageNumber]);

  const goToPrevPage = useCallback(() => {
    if (currentPage <= 1) return;
    scrollToPageNumber(currentPage - 1);
  }, [currentPage, scrollToPageNumber]);

  const runSearch = useCallback(
    (query: string) => {
      clearAllMarks();

      const hits: number[] = [];

      Object.entries(pageEls.current).forEach(([num, el]) => {
        if (!el) return;

        const count = applyPageHighlights(el, query);
        if (count > 0) hits.push(Number(num));
      });

      hits.sort((a, b) => a - b);
      setMatchPages(hits);
      setMatchIdx(0);

      if (hits.length > 0) {
        scrollToPage(hits[0]);
      }
    },
    [scrollToPage]
  );

  useEffect(() => {
    if (!searchQuery.trim()) {
      clearAllMarks();
      setMatchPages([]);
      setMatchIdx(0);
      return;
    }

    runSearch(searchQuery);
  }, [searchQuery, runSearch]);

  const goNext = useCallback(() => {
    if (matchPages.length === 0) return;

    const next = (matchIdx + 1) % matchPages.length;
    setMatchIdx(next);
    scrollToPage(matchPages[next]);
  }, [matchIdx, matchPages, scrollToPage]);

  const goPrev = useCallback(() => {
    if (matchPages.length === 0) return;

    const prev = (matchIdx - 1 + matchPages.length) % matchPages.length;
    setMatchIdx(prev);
    scrollToPage(matchPages[prev]);
  }, [matchIdx, matchPages, scrollToPage]);

  const handlePageInputSubmit = useCallback(() => {
    const page = Number(pageInput);

    if (Number.isNaN(page)) return;

    const validPage = Math.min(Math.max(page, 1), numPages);

    scrollToPageNumber(validPage);
  }, [pageInput, numPages, scrollToPageNumber]);

  const closeSearch = useCallback(() => {
    clearAllMarks();
    setMatchPages([]);
    setMatchIdx(0);
    setSearchOpen(false);
    setSearchQuery("");
  }, []);

  const handleClick = useCallback(
    (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => {
      setActive((prev) => {
        if (prev?.bboxKey === bboxKey) return null;
        return null;
      });

      requestAnimationFrame(() => {
        setActive({ findings: group, bboxKey, anchorEl: el });
      });
    },
    []
  );

  const handlePageClick = useCallback(() => setActive(null), []);

  return (
    <>
      <div className="flex items-center justify-between text-sm text-muted-foreground px-1 shrink-0">
        <div className="inline-flex items-center gap-2">
          <FileText className="h-4 w-4" />
          <span>{displayFileName}</span>
        </div>

        <button
          onClick={() => {
            if (searchOpen) {
              closeSearch();
            } else {
              setSearchOpen(true);
              setTimeout(() => searchInputRef.current?.focus(), 50);
            }
          }}
          title="Search (Ctrl+F)"
          className={`p-1 rounded hover:bg-muted transition-colors ${
            searchOpen ? "text-foreground bg-muted" : ""
          }`}
        >
          <Search className="h-4 w-4" />
        </button>
      </div>

      {searchOpen && (
        <div className="shrink-0">
          <SearchBar
            query={searchQuery}
            matchCount={matchPages.length}
            currentMatch={matchIdx}
            onQueryChange={setSearchQuery}
            onNext={goNext}
            onPrev={goPrev}
            onClose={closeSearch}
            inputRef={searchInputRef}
          />
        </div>
      )}

      {!isPdf && (
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Only PDF files are supported.
        </div>
      )}

      {isPdf && numPages > 0 && (
        <div className="flex items-center justify-between px-1 py-2 shrink-0">
          <div className="text-xs text-muted-foreground">
            Page {currentPage} of {numPages}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={goToPrevPage}
              disabled={currentPage === 1}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </button>

            {/* PAGE INPUT */}
            <div className="flex items-center gap-1 text-xs">
              <input
                type="number"
                min={1}
                max={numPages}
                value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handlePageInputSubmit();
                  }
                }}
                onBlur={handlePageInputSubmit}
                className="w-14 h-7 px-2 text-center rounded border outline-none focus:ring-1 focus:ring-blue-500"
              />
              <span className="text-muted-foreground">/ {numPages}</span>
            </div>

            <button
              onClick={goToNextPage}
              disabled={currentPage === numPages}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {displayFileName.toLowerCase().endsWith(".docx") && (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
          Please upload a .pdf file.
        </div>
      )}

      {isPdf && (
        <div
          ref={measuredRef}
          className="flex-1 overflow-y-auto rounded-lg bg-zinc-300"
          style={{ position: "relative" }}
          onClick={handlePageClick}
        >
          <Document
            file={pdfSource}
            onLoadSuccess={({ numPages }) => {
              setNumPages(numPages);
              setCurrentPage(1);
            }}
            loading={
              <div className="flex items-center justify-center h-40 text-sm text-muted-foreground animate-pulse">
                Loading document…
              </div>
            }
            error={
              <div className="flex items-center justify-center h-40 text-sm text-destructive">
                Failed to load PDF.
              </div>
            }
          >
            {Array.from({ length: numPages }, (_, i) => i + 1).map((pageNumber) => (
              <div
                key={pageNumber}
                ref={(el) => {
                  pageEls.current[pageNumber] = el;
                }}
                data-page-number={pageNumber}
                className="flex justify-center py-4"
              >
                <div
                  className="bg-white shadow-lg border border-gray-200"
                  style={{ position: "relative" }}
                >
                  <Page
                    pageNumber={pageNumber}
                    width={Math.min(containerWidth, 900)}
                    renderTextLayer
                    renderAnnotationLayer={false}
                    onRenderSuccess={(page) => {
                      setPageMetaMap((prev) => ({
                        ...prev,
                        [pageNumber]: {
                          renderedWidth: page.width,
                          renderedHeight: page.height,
                          originalWidth: page.originalWidth,
                          originalHeight: page.originalHeight,
                        },
                      }));

                      if (searchQuery.trim() && pageEls.current[pageNumber]) {
                        applyPageHighlights(pageEls.current[pageNumber]!, searchQuery);
                      }
                    }}
                  />

                  {pageMetaMap[pageNumber] && (
                    <HighlightLayer
                      pageNumber={pageNumber}
                      pageMeta={pageMetaMap[pageNumber]}
                      findings={findings}
                      activeBboxKey={active?.bboxKey ?? null}
                      onClick={handleClick}
                    />
                  )}
                </div>
              </div>
            ))}
          </Document>
        </div>
      )}

      {active && (
        <FindingPopover
          key={active.bboxKey}
          findings={active.findings}
          anchorEl={active.anchorEl}
          onClose={() => setActive(null)}
        />
      )}
    </>
  );
}

export default DocumentPreview;