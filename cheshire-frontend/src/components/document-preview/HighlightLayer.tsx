import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import type { PageMeta } from "./types";
import { groupByBbox } from "./helpers";
import { FindingOverlay } from "./FindingOverlay";

interface HighlightLayerProps {
  pageNumber: number;
  pageMeta: PageMeta;
  findings: VulnerabilityFinding[];
  activeBboxKey: string | null;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
}

export function HighlightLayer({
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
        zIndex: 5,
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