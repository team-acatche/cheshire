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
  Search,
  X,
  ChevronUp,
  ChevronDown,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// ___ pdfjs worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

// --- Types
interface PageMeta {
  renderedWidth: number;
  renderedHeight: number;
  originalWidth: number;
  originalHeight: number;
}

interface ActiveFinding {
  finding: VulnerabilityFinding;
  anchorEl: HTMLElement;
}

// --- Coordinate transform
function pdfToPixels(
  bbox: VulnerabilityFinding["bbox"],
  pageHeightPt: number,
  scale: number
) {
  return {
    left: bbox.l * scale,
    top: (pageHeightPt - bbox.t) * scale,
    width: (bbox.r - bbox.l) * scale,
    height: (bbox.r - bbox.b) * scale,
  };
}

// --- FindingOverlay
interface FindingOverlayProps {
  finding: VulnerabilityFinding;
  scale: number;
  pageHeightPt: number;
  isActive: boolean;
  onClick: (finding: VulnerabilityFinding, el: HTMLElement) => void;
}

function FindingOverlay({
  finding,
  scale,
  pageHeightPt,
  isActive,
  onClick,
}: FindingOverlayProps) {
  const rect = pdfToPixels(finding.bbox, pageHeightPt, scale);
  return (
    <div
      onClick={(e) => {
        e.stopPropagation();
        onClick(finding, e.currentTarget);
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
          ? "rgba(251, 191, 36, 0.25)"
          : "rgba(251, 191, 36, 0.12)",
        borderBottom: isActive
          ? "2.5px solid rgba(245, 158, 11, 0.9)"
          : "2px solid rgba(245, 158, 11, 0.55)",
        boxShadow: isActive
          ? "0 0 0 1.5px rgba(245, 158, 11, 0.35)"
          : "none",
        transition: "all 150ms ease",
      }}
    />
  );
}

// --- FindingPopover
interface FindingPopoverProps {
  finding: VulnerabilityFinding;
  anchorEl: HTMLElement;
}

function FindingPopover({ finding, anchorEl }: FindingPopoverProps) {
  const { refs, floatingStyles } = useFloating({
    elements: { reference: anchorEl },
    middleware: [offset(10), flip({ padding: 12 }), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
    placement: "bottom-start",
  });

  return (
    <FloatingPortal>
      <div
        ref={refs.setFloating}
        style={{ ...floatingStyles, zIndex: 9999 }}
        className="
          w-80 rounded-xl border border-amber-200/60 bg-white shadow-xl
          ring-1 ring-black/5 overflow-hidden
          dark:bg-zinc-900 dark:border-amber-400/20
          animate-in fade-in-0 zoom-in-95 duration-100
        "
      >
        {/* Header */}
        <div className="bg-amber-50 dark:bg-amber-950/40 px-4 py-3 border-b border-amber-100/80 dark:border-amber-400/15">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug">
              {finding.title}
            </p>
            <Badge
              variant="outline"
              className="shrink-0 text-[10px] border-amber-300 text-amber-700 dark:text-amber-400 dark:border-amber-600"
            >
              pg. {finding.page_no}
            </Badge>
          </div>
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
                    <ChevronRight className="size-3 mt-0.5 shrink-0 text-amber-500" />
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

// --- HighlightLayer
interface HighlightLayerProps {
  pageNumber: number;
  pageMeta: PageMeta;
  findings: VulnerabilityFinding[];
  activeFindingId: string | null;
  onClick: (finding: VulnerabilityFinding, el: HTMLElement) => void;
}

function HighlightLayer({
  pageNumber,
  pageMeta,
  findings,
  activeFindingId,
  onClick,
}: HighlightLayerProps) {
  const scale = pageMeta.renderedWidth / pageMeta.originalWidth;
  const pageFindings = findings.filter((f) => f.page_no === pageNumber);
  if (pageFindings.length === 0) return null;

  return (
    <div
      style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 20 }}
    >
      {pageFindings.map((finding, i) => (
        <FindingOverlay
          key={i}
          finding={finding}
          scale={scale}
          pageHeightPt={pageMeta.originalHeight}
          isActive={activeFindingId === makeFindingId(finding)}
          onClick={onClick}
        />
      ))}
    </div>
  );
}

// --- Stable ID helper
function makeFindingId(f: VulnerabilityFinding) {
  return `${f.page_no}-${f.bbox.l}-${f.bbox.t}`;
}

// --- SearchBar
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
          if (e.key === "Enter") e.shiftKey ? onPrev() : onNext();
          if (e.key === "Escape") onClose();
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

// --- Helpers: apply / clear search highlights in a page's text layer
// Track every <mark> we inject so we can tear them all down reliably
const injectedMarks: Set<HTMLElement> = new Set();

function getTextLayer(pageEl: HTMLElement): HTMLElement | null {
  // react-pdf v7+ uses textLayer class, older used textContent
  return (
    pageEl.querySelector(".react-pdf__Page__textLayer") ??
    pageEl.querySelector(".react-pdf__Page__textContent")
  );
}

function clearAllMarks() {
  injectedMarks.forEach((mark) => {
    const parent = mark.parentNode;
    if (parent) {
      // Replace <mark> with its text content
      parent.replaceChild(document.createTextNode(mark.textContent ?? ""), mark);
      parent.normalize(); // merge adjacent text nodes
    }
  });
  injectedMarks.clear();
}

function applyPageHighlights(pageEl: HTMLElement, query: string): number {
  const textLayer = getTextLayer(pageEl);
  if (!textLayer || !query.trim()) return 0;

  const lower = query.toLowerCase();
  let count = 0;

  // Walk leaf text nodes only
  const walker = document.createTreeWalker(textLayer, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  let node: Text | null;
  while ((node = walker.nextNode() as Text | null)) {
    textNodes.push(node);
  }

  textNodes.forEach((textNode) => {
    const text = textNode.textContent ?? "";
    const idx = text.toLowerCase().indexOf(lower);
    if (idx === -1) return;

    // Split the text node around the match and wrap only the matched portion
    const before = text.slice(0, idx);
    const match  = text.slice(idx, idx + query.length);
    const after  = text.slice(idx + query.length);

    const mark = document.createElement("mark");
    mark.textContent = match;
    mark.setAttribute("data-pdf-search", "true");
    mark.style.cssText =
      "background:rgba(59,130,246,0.35);outline:1px solid rgba(59,130,246,0.55);border-radius:2px;color:inherit;";
    injectedMarks.add(mark);

    const parent = textNode.parentNode!;
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
    const e = el as HTMLElement;
    if (isCurrent) {
      e.style.background = "rgba(234,179,8,0.55)";
      e.style.outline    = "2px solid rgba(234,179,8,0.9)";
    } else {
      e.style.background = "rgba(59,130,246,0.35)";
      e.style.outline    = "1px solid rgba(59,130,246,0.55)";
    }
  });
}

function clearPageHighlights(_pageEl: HTMLElement) {
  // no-op per page — we clear globally via clearAllMarks()
}

// --- DocumentPreview
interface DocumentPreviewProps {
  src: File | string;
  findings: VulnerabilityFinding[];
}

export function DocumentPreview({ src, findings }: DocumentPreviewProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageMetaMap, setPageMetaMap] = useState<Record<number, PageMeta>>({});
  const [active, setActive] = useState<ActiveFinding | null>(null);
  const [containerWidth, setContainerWidth] = useState(800);

  // ── Search state ──
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchPages, setMatchPages] = useState<number[]>([]); // pages with ≥1 hit
  const [matchIdx, setMatchIdx] = useState(0);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  // per-page div refs so we can scroll to them
  const pageEls = useRef<Record<number, HTMLDivElement | null>>({});

  // ── Normalise src ──
  const isUrl = typeof src === "string";
  const fileName = isUrl ? src.split("/").pop() ?? "document.pdf" : src.name;
  const isPdf = isUrl ? true : src.type === "application/pdf";
  const pdfSource: File | string = src;

  // ── ResizeObserver: re-measure whenever the panel is dragged ──
  const measuredRef = useCallback((node: HTMLDivElement | null) => {
    if (!node) return;
    setContainerWidth(node.getBoundingClientRect().width);
    const ro = new ResizeObserver(([entry]) => {
      setContainerWidth(entry.contentRect.width);
    });
    ro.observe(node);
  }, []);

  // ── Ctrl+F / Escape keyboard shortcut ──
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

  // ── Run search across all rendered page elements ──
  const runSearch = useCallback((query: string) => {
    clearAllMarks(); // tear down previous marks before injecting new ones
    const hits: number[] = [];
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (!el) return;
      const count = applyPageHighlights(el, query);
      if (count > 0) hits.push(Number(num));
    });
    // Sort ascending
    hits.sort((a, b) => a - b);
    setMatchPages(hits);
    setMatchIdx(0);
    if (hits.length > 0) scrollToPage(hits[0]);
  }, []);

  // Re-run search whenever query changes
  useEffect(() => {
    if (!searchQuery.trim()) {
      clearAllMarks();
      setMatchPages([]);
      return;
    }
    runSearch(searchQuery);
  }, [searchQuery, runSearch]);

  const scrollToPage = (pageNum: number) => {
    // Mark previous current match as normal, new one as current
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (el) markCurrentPageMatch(el, Number(num) === pageNum);
    });
    pageEls.current[pageNum]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const goNext = useCallback(() => {
    if (matchPages.length === 0) return;
    const next = (matchIdx + 1) % matchPages.length;
    setMatchIdx(next);
    scrollToPage(matchPages[next]);
  }, [matchIdx, matchPages]);

  const goPrev = useCallback(() => {
    if (matchPages.length === 0) return;
    const prev = (matchIdx - 1 + matchPages.length) % matchPages.length;
    setMatchIdx(prev);
    scrollToPage(matchPages[prev]);
  }, [matchIdx, matchPages]);

  const closeSearch = useCallback(() => {
    clearAllMarks();
    setMatchPages([]);
    setMatchIdx(0);
    setSearchOpen(false);
    setSearchQuery("");
  }, []);

  // ── Finding overlay callbacks (unchanged) ──
  const handleClick = useCallback(
    (finding: VulnerabilityFinding, el: HTMLElement) => {
      setActive((prev) =>
        prev && makeFindingId(prev.finding) === makeFindingId(finding)
          ? null
          : { finding, anchorEl: el }
      );
    },
    []
  );

  const handlePageClick = useCallback(() => setActive(null), []);
  const activeFindingId = active ? makeFindingId(active.finding) : null;

  return (
    <>
      {/* File name strip */}
      <div className="flex items-center justify-between text-sm text-muted-foreground px-1 shrink-0">
        <div className="inline-flex items-center gap-2">
          <FileText className="h-4 w-4" />
          <span>{fileName}</span>
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
          className={`p-1 rounded hover:bg-muted transition-colors ${searchOpen ? "text-foreground bg-muted" : ""}`}
        >
          <Search className="h-4 w-4" />
        </button>
      </div>

      {/* Search bar — shown when open */}
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
          Only PDF files are allowed.
        </div>
      )}

      {fileName.toLowerCase().endsWith(".docx") && (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
          Please upload a .pdf file.
        </div>
      )}

      {isPdf && (
        <div
          ref={measuredRef}
          className="flex-1 overflow-y-auto rounded-lg"
          style={{ position: "relative" }}
          onClick={handlePageClick}
        >
          <Document
            file={pdfSource}
            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
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
                ref={(el) => { pageEls.current[pageNumber] = el; }}
                style={{ position: "relative", marginBottom: 12 }}
              >
                <Page
                  pageNumber={pageNumber}
                  width={containerWidth}
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
                    // Re-apply search highlights after page (re)renders
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
                    activeFindingId={activeFindingId}
                    onClick={handleClick}
                  />
                )}
              </div>
            ))}
          </Document>
        </div>
      )}

      {/* Floating popover — unchanged */}
      {active && (
        <FindingPopover finding={active.finding} anchorEl={active.anchorEl} />
      )}
    </>
  );
}

export default DocumentPreview;