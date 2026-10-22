// cheshire-frontend/src/components/document-preview/DocumentPreview.tsx

import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import {
  FileText,
  Search,
  MessageSquareText,
  ChevronRight,
  ChevronLeft,
  Plus,
  Minus,
  ShieldAlert,
  Loader2,
  Maximize2,
  Minimize2,
  Square,
  Ban,
  RotateCw,
} from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import type { PageMeta, ActiveGroup } from "./types";
import { applyPageHighlights, clearAllMarks, markCurrentPageMatch } from "./searchHelpers";
import { SearchBar } from "./SearchBar";
import { HighlightLayer } from "./HighlightLayer";
import { FindingPopover } from "./FindingPopover";
import { PdfPageSkeleton } from "./PdfPageSkeleton";
import { isUnanchored } from "./helpers";
import { DocumentLevelFindings } from "./DocumentLevelFindings";
import { SeverityLegend } from "./SeverityLegend";
import { TONES, bySeverity, countByTone, dominantTone, getTone, toneColor, type Tone } from "./severity";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// ─── pdfjs worker ────────────────────────────────────────────────────────────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

// ─── Debounce helper ─────────────────────────────────────────────────────────
function debounce<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout>;
  return ((...args: any[]) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  }) as T;
}

// ─── DocumentPreview ─────────────────────────────────────────────────────────
interface DocumentPreviewProps {
  src: File | string;
  findings: VulnerabilityFinding[];
  fileName?: string;
  findingsLoading?: boolean;
  chatOpen?: boolean;
  onToggleChat?: () => void;
  onCancelAnalysis?: () => void;
  onRerunAnalysis?: () => void;
}

export function DocumentPreview({ src, findings, fileName, findingsLoading = false, chatOpen = false, onToggleChat, onCancelAnalysis, onRerunAnalysis }: DocumentPreviewProps) {
  const [numPages, setNumPages]             = useState<number>(0);
  const [pageMetaMap, setPageMetaMap]       = useState<Record<number, PageMeta>>({});
  const [active, setActive]                 = useState<ActiveGroup | null>(null);
  const [containerWidth, setContainerWidth] = useState(800);
  // pdfLoading stays true until onLoadSuccess fires — drives the skeleton
  const [pdfLoading, setPdfLoading]         = useState(true);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const [pageInput, setPageInput]     = useState("1");
  const [zoomLevel, setZoomLevel]     = useState(1);
  const zoomPercentage = Math.round(zoomLevel * 100);
  const MIN_ZOOM  = 0.5;
  const MAX_ZOOM  = 2;
  const ZOOM_STEP = 0.1;

  // Search
  const [searchOpen, setSearchOpen]   = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchPages, setMatchPages]   = useState<number[]>([]);
  const [matchIdx, setMatchIdx]       = useState(0);

  const searchInputRef = useRef<HTMLInputElement>(null);
  const pageEls        = useRef<Record<number, HTMLDivElement | null>>({});
  const roRef          = useRef<ResizeObserver | null>(null);

  // ── Full screen (PDF viewer only, not the whole app) ───────────────────────
  const fullscreenRef = useRef<HTMLDivElement | null>(null);
  // Stored in state too, so portals (popovers) get a real element after mount
  const [portalEl, setPortalEl] = useState<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Stable callback ref (must not change between renders)
  const setFullscreenEl = useCallback((node: HTMLDivElement | null) => {
    fullscreenRef.current = node;
    setPortalEl(node);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = fullscreenRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      el.requestFullscreen().catch(() => {});
    }
  }, []);

  useEffect(() => {
    const onChange = () =>
      setIsFullscreen(document.fullscreenElement === fullscreenRef.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  // ── Derived ────────────────────────────────────────────────────────────────
  const isUrl           = typeof src === "string";
  const displayFileName = fileName ?? (isUrl ? "document.pdf" : (src as File).name);
  const isPdf           = isUrl ? true : (src as File).type === "application/pdf";

  // Reset when the source changes (switching between sessions)
  useEffect(() => {
    setPdfLoading(true);
    setNumPages(0);
    setPageMetaMap({});
    setCurrentPage(1);
    setPageInput("1");
    setActive(null);
  }, [src]);

  // ── Page width ─────────────────────────────────────────────────────────────
  // Snapping containerWidth to the nearest 10 px before computing pageWidth
  // means that tiny ResizeObserver jitter never triggers a cascade of re-renders.
  // In fullscreen the max page width is raised so the PDF uses the extra space.
  const pageWidth = useMemo(() => {
    const snapped = Math.round(containerWidth / 10) * 10;
    return Math.min(snapped, isFullscreen ? 1400 : 900) * zoomLevel;
  }, [containerWidth, zoomLevel, isFullscreen]);

  // ── ResizeObserver — debounced + threshold gated ───────────────────────────
  const debouncedSetWidth = useCallback(
    debounce((newWidth: number) => {
      setContainerWidth((prev) => (Math.abs(prev - newWidth) > 8 ? newWidth : prev));
    }, 150),
    []
  );

  const measuredRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (roRef.current) { roRef.current.disconnect(); roRef.current = null; }
      if (!node) return;

      // Measure immediately on first attach (no debounce needed)
      setContainerWidth(node.getBoundingClientRect().width);
      const ro = new ResizeObserver(([entry]) => debouncedSetWidth(entry.contentRect.width));
      ro.observe(node);
      roRef.current = ro;
    },
    [debouncedSetWidth]
  );

  // ── Keyboard shortcuts ─────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "f") {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
      if (e.key === "Escape") { setSearchOpen(false); setSearchQuery(""); }
      if ((e.ctrlKey || e.metaKey) && (e.key === "+" || e.key === "=")) {
        e.preventDefault(); setZoomLevel((p) => Math.min(p + 0.1, MAX_ZOOM));
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "-") {
        e.preventDefault(); setZoomLevel((p) => Math.max(p - 0.1, MIN_ZOOM));
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "0") {
        e.preventDefault(); setZoomLevel(1);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => { setPageInput(String(currentPage)); }, [currentPage]);

  // ── IntersectionObserver ───────────────────────────────────────────────────
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .map((e) => ({ page: Number((e.target as HTMLElement).dataset.pageNumber), ratio: e.intersectionRatio }))
          .sort((a, b) => b.ratio - a.ratio);
        if (visible.length > 0) setCurrentPage(visible[0].page);
      },
      { root: null, threshold: [0.25, 0.5, 0.75] }
    );
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (el) { el.dataset.pageNumber = num; observer.observe(el); }
    });
    return () => observer.disconnect();
  }, [numPages]);

  // ── Scroll helpers ─────────────────────────────────────────────────────────
  const scrollToPage = useCallback((pageNum: number) => {
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (el) markCurrentPageMatch(el, Number(num) === pageNum);
    });
    pageEls.current[pageNum]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const scrollToPageNumber = useCallback((pageNum: number) => {
    const el = pageEls.current[pageNum];
    if (!el) return;
    setCurrentPage(pageNum);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const goToNextPage = useCallback(() => {
    if (currentPage < numPages) scrollToPageNumber(currentPage + 1);
  }, [currentPage, numPages, scrollToPageNumber]);

  const goToPrevPage = useCallback(() => {
    if (currentPage > 1) scrollToPageNumber(currentPage - 1);
  }, [currentPage, scrollToPageNumber]);

  const handleZoomIn    = useCallback(() => setZoomLevel((p) => Math.min(p + ZOOM_STEP, MAX_ZOOM)), []);
  const handleZoomOut   = useCallback(() => setZoomLevel((p) => Math.max(p - ZOOM_STEP, MIN_ZOOM)), []);
  const handleResetZoom = useCallback(() => setZoomLevel(1), []);

  // ── Search ─────────────────────────────────────────────────────────────────
  const runSearch = useCallback((query: string) => {
    clearAllMarks();
    const hits: number[] = [];
    Object.entries(pageEls.current).forEach(([num, el]) => {
      if (el && applyPageHighlights(el, query) > 0) hits.push(Number(num));
    });
    hits.sort((a, b) => a - b);
    setMatchPages(hits);
    setMatchIdx(0);
    if (hits.length > 0) scrollToPage(hits[0]);
  }, [scrollToPage]);

  useEffect(() => {
    if (!searchQuery.trim()) { clearAllMarks(); setMatchPages([]); setMatchIdx(0); return; }
    runSearch(searchQuery);
  }, [searchQuery, runSearch]);

  const goNext = useCallback(() => {
    if (!matchPages.length) return;
    const next = (matchIdx + 1) % matchPages.length;
    setMatchIdx(next); scrollToPage(matchPages[next]);
  }, [matchIdx, matchPages, scrollToPage]);

  const goPrev = useCallback(() => {
    if (!matchPages.length) return;
    const prev = (matchIdx - 1 + matchPages.length) % matchPages.length;
    setMatchIdx(prev); scrollToPage(matchPages[prev]);
  }, [matchIdx, matchPages, scrollToPage]);

  const handlePageInputSubmit = useCallback(() => {
    const page = Number(pageInput);
    if (Number.isNaN(page)) return;
    scrollToPageNumber(Math.min(Math.max(page, 1), numPages));
  }, [pageInput, numPages, scrollToPageNumber]);

  const closeSearch = useCallback(() => {
    clearAllMarks(); setMatchPages([]); setMatchIdx(0);
    setSearchOpen(false); setSearchQuery("");
  }, []);

  // severity filter (driven by the legend chips)
  const [hiddenTones, setHiddenTones] = useState<Set<Tone>>(new Set());
  const toneCounts = useMemo(() => countByTone(findings), [findings]);

  const toggleTone = useCallback((t: Tone) => {
    setActive(null);
    setHiddenTones((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      return next;
    });
  }, []);

  const { anchored, documentLevel } = useMemo(() => {
    const shown = findings.filter((f) => !hiddenTones.has(getTone(f)));
    return {
      anchored: shown.filter((f) => !isUnanchored(f)),
      documentLevel: shown.filter(isUnanchored),
    };
  }, [findings, hiddenTones]);

  // ── Findings grouping (memoised) ───────────────────────────────────────────
  const groupedFindings = useMemo(() => {
    return [...findings]
      .sort((a, b) => a.page_no - b.page_no || bySeverity(a, b))
      .reduce((acc, f) => {
        const key = isUnanchored(f) ? "Document-wide" : String(f.page_no);
        (acc[key] ??= []).push(f);
        return acc;
      }, {} as Record<string, VulnerabilityFinding[]>);
  }, [findings]);

  const handleClick = useCallback(
    (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => {
      setActive((prev) => (prev?.bboxKey === bboxKey ? null : null));
      requestAnimationFrame(() => setActive({ findings: group, bboxKey, anchorEl: el }));
    },
    []
  );

  const handlePageClick = useCallback(() => setActive(null), []);

  // state/refs
  const docBtnRef = useRef<HTMLButtonElement>(null);

  // open the popover anchored to the stable toolbar pill (not the list item, which unmounts)
  const handleDocLevelSelect = useCallback((f: VulnerabilityFinding) => {
    if (!docBtnRef.current) return;
    setActive({ findings: [f], bboxKey: `doc|${f.title}`, anchorEl: docBtnRef.current });
  }, []);

  const handleFocusChange = useCallback((f: VulnerabilityFinding | null) => {
    setActive((prev) => (prev ? { ...prev, focused: f ?? undefined } : prev));
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div
      ref={setFullscreenEl}
      className={`flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-hidden ${
        isFullscreen ? "bg-background p-4" : ""
      }`}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between text-sm text-muted-foreground px-1 shrink-0">
        <div className="inline-flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 shrink-0" />
          <span className="truncate">{displayFileName}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => {
              if (searchOpen) closeSearch();
              else { setSearchOpen(true); setTimeout(() => searchInputRef.current?.focus(), 50); }
            }}
            title="Search (Ctrl+F)"
            className={`p-1 rounded hover:bg-muted transition-colors ${searchOpen ? "text-foreground bg-muted" : ""}`}
          >
            <Search className="h-4 w-4" />
          </button>

          {onToggleChat && !isFullscreen && (
            <button
              onClick={onToggleChat}
              title={chatOpen ? "Hide chatbot" : "Show chatbot"}
              aria-pressed={chatOpen}
              className={`p-1 rounded hover:bg-muted transition-colors ${chatOpen ? "text-foreground bg-muted" : ""}`}
            >
              <MessageSquareText className="h-4 w-4" />
            </button>
          )}

          <button
            onClick={toggleFullscreen}
            title={isFullscreen ? "Exit full screen (Esc)" : "Full screen"}
            aria-pressed={isFullscreen}
            className={`p-1 rounded hover:bg-muted transition-colors ${isFullscreen ? "text-foreground bg-muted" : ""}`}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {searchOpen && (
        <div className="shrink-0">
          <SearchBar
            query={searchQuery} matchCount={matchPages.length} currentMatch={matchIdx}
            onQueryChange={setSearchQuery} onNext={goNext} onPrev={goPrev}
            onClose={closeSearch} inputRef={searchInputRef}
          />
        </div>
      )}

      {!isPdf && (
        <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
          Only PDF files are supported.
        </div>
      )}

      {/* Toolbar — only once the PDF has loaded */}
      {isPdf && numPages > 0 && (
        <div className="grid grid-cols-3 items-center px-1 py-2 shrink-0 gap-3">
          {/* Left — findings badge OR loading indicator */}
          <div className="justify-self-start flex items-center gap-2">
            {findingsLoading ? (
              <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Analyzing document…
                {onCancelAnalysis && (
                  <button
                  type="button"
                  onClick={onCancelAnalysis}
                  className="-mr-1 rounded-full border border-red-600 p-1 hover:bg-red-100 dark:border-red-400 dark:hover:bg-red-950"
                  aria-label="Cancel analysis"
                  title="Cancel analysis"
                >
                  <Square className="h-3 w-3 text-red-600 dark:text-red-400" />
                </button>
                )}
              </div>
            ) : onRerunAnalysis ? (
              <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm text-xs text-muted-foreground">
                <Ban className="h-3.5 w-3.5" />
                Analysis cancelled
                <button
                  type="button"
                  onClick={onRerunAnalysis}
                  className="-mr-1 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-foreground hover:bg-muted transition-colors"
                  title="Re-run analysis"
                >
                  <RotateCw className="h-3 w-3" />
                  Re-run
                </button>
              </div>
            ) :(
              <Popover>
                <PopoverTrigger asChild>
                  <button className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm hover:bg-muted transition-colors">
                    <ShieldAlert className={`h-3.5 w-3.5 ${findings.length ? TONES[dominantTone(findings)].text : "text-muted-foreground"}`} />
                    <span className="text-xs text-muted-foreground">Total Findings</span>
                    <span className="text-sm font-semibold text-foreground">{findings.length}</span>
                  </button>
                </PopoverTrigger>
                <PopoverContent
                  container={portalEl}
                  className="w-90 p-0 border bg -background shadow-md scroll-transparent"
                  align="start"
                >
                  <div className="px-3 py-2 border-b bg-muted/40">
                    <div className="text-sm font-semibold">Findings</div>
                    <div className="text-xs text-muted-foreground">Jump directly to a finding</div>
                  </div>
                  <div className="max-h-72 overflow-y-auto">
                    {Object.entries(groupedFindings).map(([page, pf]) => (
                      <div key={page} className="mb-2">
                        <div className="px-3 py-1 text-[11px] font-semibold text-muted-foreground uppercase">{page === "Document-wide" ? page : `Page ${page}`}</div>
                        {pf.map((finding, idx) => (
                          <button
                            key={`${finding.page_no}-${finding.bbox.l}-${finding.bbox.t}-${idx}`}
                            onClick={() =>
                              isUnanchored(finding) ? handleDocLevelSelect(finding) : scrollToPageNumber(finding.page_no)
                            }
                            className="w-full px-3 py-2 text-left hover:bg-muted transition-colors"
                          >
                            <div className="flex items-center gap-2">
                              <span className="size-2 shrink-0 rounded-full" style={{ background: toneColor(getTone(finding)) }} />
                              <span className="text-sm font-medium truncate">{finding.title || `Finding ${idx + 1}`}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
            {!findingsLoading && (
              <DocumentLevelFindings
                ref={docBtnRef}
                findings={documentLevel}
                onSelect={handleDocLevelSelect}
                container={portalEl}
              />
            )}
          </div>

          {/* Center — zoom */}
          <div className="justify-self-center">
            <div className="flex items-center gap-1 rounded border px-1 py-1 bg-background">
              <button onClick={handleZoomOut} disabled={zoomLevel <= MIN_ZOOM}
                className="p-1 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed">
                <Minus className="h-4 w-4" />
              </button>
              <button onClick={handleResetZoom} className="min-w-14 text-xs tabular-nums px-2">
                {zoomPercentage}%
              </button>
              <button onClick={handleZoomIn} disabled={zoomLevel >= MAX_ZOOM}
                className="p-1 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed">
                <Plus className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Right — pagination */}
          <div className="justify-self-end flex items-center gap-2">
            <button onClick={goToPrevPage} disabled={currentPage === 1}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed">
              <ChevronLeft className="h-3.5 w-3.5" /> Previous
            </button>
            <div className="flex items-center gap-1 text-xs">
              <input type="number" min={1} max={numPages} value={pageInput}
                onChange={(e) => setPageInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handlePageInputSubmit(); }}
                onBlur={handlePageInputSubmit}
                className="w-14 h-7 px-2 text-center rounded border outline-none focus:ring-1 focus:ring-blue-500"
              />
              <span className="text-muted-foreground">/ {numPages}</span>
            </div>
            <button onClick={goToNextPage} disabled={currentPage === numPages}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed">
              Next <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
      {isPdf && numPages > 0 && !findingsLoading && findings.length > 0 && (
        <SeverityLegend counts={toneCounts} hidden={hiddenTones} onToggle={toggleTone} />
      )}

      {displayFileName.toLowerCase().endsWith(".docx") && (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
          Please upload a .pdf file.
        </div>
      )}

      {isPdf && (
        <>
          {pdfLoading && (
            <div className="flex-1 overflow-hidden rounded-lg bg-zinc-300">
              <PdfPageSkeleton zoomLevel={zoomLevel} />
            </div>
          )}

          <div
            ref={measuredRef}
            className="flex-1 overflow-auto rounded-lg bg-zinc-300 scroll-transparent"
            style={{ position: "relative", display: pdfLoading ? "none" : "block" }}
            onClick={handlePageClick}
          >
            <Document
              file={src}
              onLoadSuccess={({ numPages: n }) => {
                setNumPages(n);
                setCurrentPage(1);
                setPdfLoading(false);
              }}
              onLoadError={() => setPdfLoading(false)}
              loading={null}
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
                  data-page-number={pageNumber}
                  className="flex justify-center py-4"
                >
                  <div className="bg-white shadow-lg border border-gray-200" style={{ position: "relative" }}>
                    <Page
                      pageNumber={pageNumber}
                      width={pageWidth}
                      renderTextLayer
                      renderAnnotationLayer={false}
                      onRenderSuccess={(page) => {
                        setPageMetaMap((prev) => ({
                          ...prev,
                          [pageNumber]: {
                            renderedWidth:  page.width,
                            renderedHeight: page.height,
                            originalWidth:  page.originalWidth,
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
                        findings={anchored}
                        activeFindings={active?.findings ?? null}
                        focusedFinding={active?.focused ?? null}
                        onClick={handleClick}
                      />
                    )}
                  </div>
                </div>
              ))}
            </Document>
          </div>
        </>
      )}

      {active && (
        <FindingPopover
          key={active.bboxKey}
          findings={active.findings}
          anchorEl={active.anchorEl}
          onClose={() => setActive(null)}
          onFocusChange={handleFocusChange}
          portalRoot={portalEl}
        />
      )}
    </div>
  );
}

export default DocumentPreview;