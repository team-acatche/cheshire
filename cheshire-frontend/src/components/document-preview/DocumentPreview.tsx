import { useState, useRef, useCallback, useEffect } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import {
  FileText,
  Search,
  ChevronRight,
  ChevronLeft,
  Plus,
  Minus,
  ShieldAlert,
} from "lucide-react";
<<<<<<< HEAD
=======
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
>>>>>>> @{-1}
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import type { PageMeta, ActiveGroup } from "./types";
import { applyPageHighlights, clearAllMarks, markCurrentPageMatch } from "./searchHelpers";
import { SearchBar } from "./SearchBar";
import { HighlightLayer } from "./HighlightLayer";
import { FindingPopover } from "./FindingPopover";
import { PdfPageSkeleton} from "./PdfPageSkeleton";
 
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
 
// ─── pdfjs worker ────────────────────────────────────────────────────────────
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();
 
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
  const [zoomLevel, setZoomLevel] = useState(1);
  const zoomPercentage = Math.round(zoomLevel * 100);
 
  const MIN_ZOOM = 0.5;
  const MAX_ZOOM = 2;
  const ZOOM_STEP = 0.1;
 
  const handleZoomIn = useCallback(() => {
    setZoomLevel((prev) => Math.min(prev + ZOOM_STEP, MAX_ZOOM));
  }, []);
 
  const handleZoomOut = useCallback(() => {
    setZoomLevel((prev) => Math.max(prev - ZOOM_STEP, MIN_ZOOM));
  }, []);
 
  const handleResetZoom = useCallback(() => {
    setZoomLevel(1);
  }, []);
 
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
 
      if ((e.ctrlKey || e.metaKey) && (e.key === "+" || e.key === "=")) {
        e.preventDefault();
        setZoomLevel((prev) => Math.min(prev + 0.1, 2));
      }
 
      if ((e.ctrlKey || e.metaKey) && e.key === "-") {
        e.preventDefault();
        setZoomLevel((prev) => Math.max(prev - 0.1, 0.5));
      }
 
      if ((e.ctrlKey || e.metaKey) && e.key === "0") {
        e.preventDefault();
        setZoomLevel(1);
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
<<<<<<< HEAD
=======

  const sortedFindings = [...findings].sort(
  (a, b) => a.page_no - b.page_no
  );

  const groupedFindings = sortedFindings.reduce((acc, finding) => {
  if (!acc[finding.page_no]) {
    acc[finding.page_no] = [];
  }
  acc[finding.page_no].push(finding);
  return acc;
}, {} as Record<number, typeof findings>);
>>>>>>> @{-1}
 
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
        <div className="inline-flex items-center gap-2 min-w-0">
          <FileText className="h-4 w-4 shrink-0" />
          <span className="truncate">{displayFileName}</span>
        </div>
 
        <div className="flex items-center gap-2">
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
        <div className="grid grid-cols-3 items-center px-1 py-2 shrink-0 gap-3">
<<<<<<< HEAD
          {/* LEFT: findings count */}
          <div className="justify-self-start">
            <div className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm">
              <ShieldAlert className="h-3.5 w-3.5 text-yellow-500" />
              <span className="text-xs text-muted-foreground">  
                Total Findings
              </span>
              <span className="text-sm font-semibold text-foreground">
                {findings.length}
              </span>
            </div>
          </div>
=======
          {/* LEFT: total findings count */}
          <div className="justify-self-start">
          <Popover>
            <PopoverTrigger asChild>
              <button className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm hover:bg-muted transition-colors">
                <ShieldAlert className="h-3.5 w-3.5 text-yellow-500" />
                <span className="text-xs text-muted-foreground">
                  Total Findings
                </span>
                <span className="text-sm font-semibold text-foreground">
                  {findings.length}
                </span>
              </button>
            </PopoverTrigger>

            <PopoverContent
              className="w-[360px] p-0 border bg-background shadow-md"
              align="start"
            >
              {/* Header */}
              <div className="px-3 py-2 border-b bg-muted/40">
                <div className="text-sm font-semibold text-foreground">
                  Findings
                </div>
                <div className="text-xs text-muted-foreground">
                  Jump directly to a finding
                </div>
              </div>

              {/* List */}
              <div className="max-h-72 overflow-y-auto">
                {Object.entries(groupedFindings).map(([page, pageFindings]) => (
                  <div key={page} className="mb-2">
                    
                    {/* Page header */}
                    <div className="px-3 py-1 text-[11px] font-semibold text-muted-foreground uppercase">
                      Page {page}
                    </div>

                    {/* Findings under page */}
                    {pageFindings.map((finding, index) => (
                      <button
                        key={`${finding.page_no}-${finding.bbox.l}-${finding.bbox.t}`}
                        onClick={() => {
                          scrollToPageNumber(finding.page_no);
                        }}
                        className="w-full px-3 py-2 text-left transition-colors
                                  hover:bg-amber-100/60"
                      >
                        <div className="text-sm font-medium text-foreground truncate">
                          {finding.title || `Finding ${index + 1}`}
                        </div>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </PopoverContent>
          </Popover>
        </div>
>>>>>>> @{-1}
        
          {/* CENTER: zoom controls */}
          <div className="justify-self-center">
            <div className="flex items-center gap-1 rounded border px-1 py-1 bg-background">
              <button
                onClick={handleZoomOut}
                disabled={zoomLevel <= MIN_ZOOM}
                title="Zoom out"
                className="p-1 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Minus className="h-4 w-4" />
              </button>
 
              <button
                onClick={handleResetZoom}
                title="Reset zoom"
                className="min-w-14 text-xs tabular-nums px-2"
              >
                {zoomPercentage}%
              </button>
 
              <button
                onClick={handleZoomIn}
                disabled={zoomLevel >= MAX_ZOOM}
                title="Zoom in"
                className="p-1 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
          </div>
 
          {/* RIGHT: pagination */}
          <div className="justify-self-end flex items-center gap-2">
            <button
              onClick={goToPrevPage}
              disabled={currentPage === 1}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </button>
 
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
          className="flex-1 overflow-auto rounded-lg bg-zinc-300"
          style={{ position: "relative" }}
          onClick={handlePageClick}
        >
          <Document
            file={pdfSource}
            onLoadSuccess={({ numPages }) => {
              setNumPages(numPages);
              setCurrentPage(1);
            }}
            loading={<PdfPageSkeleton zoomLevel={zoomLevel} />}
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
                    width={Math.min(containerWidth, 900) * zoomLevel}
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