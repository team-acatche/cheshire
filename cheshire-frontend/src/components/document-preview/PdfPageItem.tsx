import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Page } from "react-pdf";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import type { PageMeta } from "./types";
import { HighlightLayer } from "./HighlightLayer";
import { ScanOverlay } from "./AnalysisProgress";

interface PdfPageItemProps {
  pageNumber: number;
  pageWidth: number;
  meta?: PageMeta;
  anchored: VulnerabilityFinding[];
  activeFindings: VulnerabilityFinding[] | null;
  focusedFinding: VulnerabilityFinding | null;
  onHighlightClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
  onRendered: (pageNumber: number, meta: PageMeta) => void;
  registerEl: (pageNumber: number, el: HTMLDivElement | null) => void;
  showScan: boolean;
  scanActive: boolean;
  scanned: boolean;
}

// Height/width ratio learned from the first rendered page (A4 until then).
// Used to size placeholders so scrolling to a not-yet-rendered page lands close.
let knownRatio = 1.414;

function getScrollParent(el: HTMLElement | null): HTMLElement | null {
  let p = el?.parentElement ?? null;
  while (p) {
    const o = getComputedStyle(p).overflowY;
    if (o === "auto" || o === "scroll") return p;
    p = p.parentElement;
  }
  return null;
}

export const PdfPageItem = memo(function PdfPageItem({
  pageNumber, pageWidth, meta, anchored, activeFindings, focusedFinding,
  onHighlightClick, onRendered, registerEl, showScan, scanActive, scanned,
}: PdfPageItemProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  // Pages render lazily once they get near the viewport, then stay mounted.
  const [shouldRender, setShouldRender] = useState(pageNumber <= 2);

  const setRef = useCallback(
    (el: HTMLDivElement | null) => {
      wrapRef.current = el;
      registerEl(pageNumber, el);
    },
    [registerEl, pageNumber]
  );

  useEffect(() => {
    if (shouldRender) return;
    const el = wrapRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setShouldRender(true);
          observer.disconnect();
        }
      },
      { root: getScrollParent(el), rootMargin: "1500px 0px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [shouldRender]);

  const handleRenderSuccess = useCallback(
    (page: { width: number; height: number; originalWidth: number; originalHeight: number }) => {
      if (page.width > 0) knownRatio = page.height / page.width;
      onRendered(pageNumber, {
        renderedWidth: page.width,
        renderedHeight: page.height,
        originalWidth: page.originalWidth,
        originalHeight: page.originalHeight,
      });
    },
    [onRendered, pageNumber]
  );

  return (
    <div ref={setRef} data-page-number={pageNumber} className="flex justify-center py-4">
      <div
        className="bg-white shadow-lg border border-gray-200"
        style={
          shouldRender
            ? { position: "relative" }
            : { position: "relative", width: pageWidth, height: meta?.renderedHeight ?? pageWidth * knownRatio }
        }
      >
        {shouldRender && (
          <>
            <Page
              pageNumber={pageNumber}
              width={pageWidth}
              renderTextLayer
              renderAnnotationLayer={false}
              onRenderSuccess={handleRenderSuccess}
            />
            {showScan && <ScanOverlay active={scanActive} scanned={scanned} />}
            {meta && (
              <HighlightLayer
                pageNumber={pageNumber}
                pageMeta={meta}
                findings={anchored}
                activeFindings={activeFindings}
                focusedFinding={focusedFinding}
                onClick={onHighlightClick}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
});