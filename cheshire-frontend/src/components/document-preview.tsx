import { useState, useRef, useCallback } from "react";
import { Document, Page, pdfjs} from "react-pdf";
import {
  useFloating,
  offset,
  flip,
  shift,
  autoUpdate,
  FloatingPortal,
} from "@floating-ui/react"
import { FileText, ExternalLink, ChevronRight} from "lucide-react";
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
  originalWidth: number; // in PDF points
  originalHeight: number; // in PDF points
}

interface ActiveFinding {
  finding: VulnerabilityFinding;
  anchorEl: HTMLElement;
}


// --- Coordinate transform


function pdfToPixels (
  bbox:  VulnerabilityFinding["bbox"],
  pageHeightPt: number,
  scale: number
) {
  return {
    left:   bbox.l * scale,
    top:    (pageHeightPt - bbox.t) * scale,
    width:  (bbox.r - bbox.l) * scale,
    height: (bbox.r - bbox.b) * scale,
  };
}


// --- FindingOverlay
interface FindingOverlayProps {
  finding: VulnerabilityFinding;
  scale: number;
  pageHeightPt: number;
  isActive: boolean;
  onEnter: (finding: VulnerabilityFinding, el: HTMLElement) => void;
  onLeave: () => void;
}

function FindingOverlay({
  finding,
  scale,
  pageHeightPt,
  isActive,
  onEnter,
  onLeave,
}: FindingOverlayProps) {
  const rect = pdfToPixels(finding.bbox, pageHeightPt, scale);

  return (
    <div
      onMouseEnter={(e) => onEnter(finding, e.currentTarget)}
      onMouseLeave={onLeave}
      onClick={(e) => onEnter(finding, e.currentTarget)}
      style={{
        position: "absolute",
        left:     rect.left,
        top:      rect.top,
        width:    rect.width,
        height:   rect.height,
        pointerEvents: "all",
        cursor:   "pointer",
        borderRadius: 3,
        //Idle state: soft amber underline
        background: isActive
          ? "rgba(251, 191, 36, 0.25)"
          : "rgba(251, 191, 36, 0.12)",
        borderBottom: isActive
          ? "2.5px solid rgba(245, 158, 11, 0.9)"
          : "2px solid rgba(245, 158, 11, 0.55)",
        boxShadow: isActive
          ? "0 0 0 1.5px rgba(245, 158, 11, 0.35)"
          : "none",
        transition: "all 150ms ease"
      }}
    />
  );
}


// --- FindingPopover
interface FindingPopoverProps {
  finding: VulnerabilityFinding;
  anchorEl: HTMLElement;
  onClose: () => void;
}

function FindingPopover({ finding, anchorEl, onClose}: FindingPopoverProps) {
  const { refs, floatingStyles} = useFloating({
    elements: { reference: anchorEl },
    middleware: [offset(10), flip({ padding: 12}), shift({ padding: 12})],
    whileElementsMounted: autoUpdate,
    placement: "bottom-start",
  });

  return(
    <FloatingPortal>
      <div
        ref={refs.setFloating}
        style={{ ...floatingStyles, zIndex: 9999 }}
        onMouseEnter={() => {/* keep open while hovering popover */}}
        onMouseLeave={onClose}
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
                  <li key={i} className="flex gap-2 text-xs text-zinc-700 dark:text-zinc-300 leading-snug">
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
  onEnter: (finding: VulnerabilityFinding, el: HTMLElement) => void;
  onLeave: () => void;
}

function HighlightLayer({
  pageNumber,
  pageMeta,
  findings,
  activeFindingId,
  onEnter,
  onLeave,
}: HighlightLayerProps) {
  const scale = pageMeta.renderedWidth / pageMeta.originalWidth;
  const pageFindings = findings.filter((f) => f.page_no === pageNumber);

  if(pageFindings.length === 0) return null;

  return(
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        zIndex:20,
      }}
    >
      {pageFindings.map((finding, i) => (
        <FindingOverlay
          key={i}
          finding={finding}
          scale={scale}
          pageHeightPt={pageMeta.originalHeight}
          isActive={activeFindingId === makeFindingId(finding)}
          onEnter={onEnter}
          onLeave={onLeave}
        />
      ))}
    </div>
  );
}

// --- Stable ID helper
function makeFindingId(f: VulnerabilityFinding) {
  return `${f.page_no}-${f.bbox.l}-${f.bbox.t}`;
}

// --- DocumentPreview 
interface DocumentPreviewProps {
  src: File | string; // string = direct API URL
  findings: VulnerabilityFinding[];
}

export function DocumentPreview({ src, findings }: DocumentPreviewProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageMetaMap, setPageMetaMap] = useState<Record<number, PageMeta>>({});
  const [active, setActive] = useState<ActiveFinding | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  // ── Normalise src so the rest of the component never touches the union ──
  const isUrl    = typeof src === "string";
  const fileName = isUrl ? src.split("/").pop() ?? "document.pdf" : src.name;
  const isPdf    = isUrl ? true : src.type === "application/pdf";
  // react-pdf <Document file={}> accepts File, URL string, or ArrayBuffer
  const pdfSource: File | string = src;

  // Width of rendered pages - fill the container
  const [containerWidth, setContainerWidth] = useState(800);
  const measuredRef = useCallback((node: HTMLDivElement | null) => {
    if (node) setContainerWidth(node.getBoundingClientRect().width);
  }, []);

  const handleEnter = useCallback(
    (finding: VulnerabilityFinding, el: HTMLElement) => {
      setActive({ finding, anchorEl: el});
    },
    []
  );

  const handleLeave = useCallback(() => {
    // Small delay so the pointer can reach the popover without it vanishing
    setTimeout(() => setActive(null), 80);
  }, []);

  const activeFindingId = active ? makeFindingId(active.finding) : null;
    
  return (
    <>
      {/* File name strip */}
      <div className="inline-flex items-center gap-2 text-sm text-muted-foreground px-1">
        <FileText className="h-4 w-4" />
        <span>{fileName}</span>
      </div>

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
          ref={(node) => {
            (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
            measuredRef(node);
          }}
          className="flex-1 overflow-y-auto rounded-lg"
          style={{ position:"relative" }}
        >
          <Document
            file={pdfSource}
            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
            loading={
              <div className="flex items-center justify-center h-40 text-sm text-muted-foreground animate-pulse">
                
                Loading document... 
              </div>
            }
            error={
              <div className="flex items-center justify-center h-40 text-sm text-destructive">

                Failed to load PDF.
              </div>
            }
          >
            {Array.from({ length: numPages}, (_, i) => i + 1).map((pageNumber) => (
              <div
                key={pageNumber}
                style={{position: "relative", marginBottom: 12}}
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
                        // page.originalWidth / originalHeight are in PDF points
                        originalWidth: page.originalWidth,
                        originalHeight: page.originalHeight,
                      },
                    }));
                  }}
                />

                {pageMetaMap[pageNumber] && (
                  <HighlightLayer
                    pageNumber={pageNumber}
                    pageMeta={pageMetaMap[pageNumber]}
                    findings={findings}
                    activeFindingId={activeFindingId}
                    onEnter={handleEnter}
                    onLeave={handleLeave}
                />
                )}
              </div>
            ))}
          </Document>
        </div>
      )}


      {/* Floating popover — rendered outside the scroll container via portal */}
      {active && (
        <FindingPopover
          finding={active.finding}
          anchorEl={active.anchorEl}
          onClose={() => setActive(null)}
        />
      )}
    </>
  );
}

export default DocumentPreview;