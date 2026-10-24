import { memo, useCallback } from "react";
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

export const PdfPageItem = memo(function PdfPageItem({
  pageNumber, pageWidth, meta, anchored, activeFindings, focusedFinding,
  onHighlightClick, onRendered, registerEl, showScan, scanActive, scanned,
}: PdfPageItemProps) {
  const setRef = useCallback(
    (el: HTMLDivElement | null) => registerEl(pageNumber, el),
    [registerEl, pageNumber]
  );

  const handleRenderSuccess = useCallback(
    (page: { width: number; height: number; originalWidth: number; originalHeight: number }) =>
      onRendered(pageNumber, {
        renderedWidth: page.width,
        renderedHeight: page.height,
        originalWidth: page.originalWidth,
        originalHeight: page.originalHeight,
      }),
    [onRendered, pageNumber]
  );

  return (
    <div ref={setRef} data-page-number={pageNumber} className="flex justify-center py-4">
      <div className="bg-white shadow-lg border border-gray-200" style={{ position: "relative" }}>
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
      </div>
    </div>
  );
});