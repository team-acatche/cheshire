import type { CSSProperties } from "react";
import type { VulnerabilityFinding, BoundingBox } from "@/types/VulnerabilityFinding";
import { pdfToPixels } from "./helpers";
import { TONES, dominantTone, getTone, isTentative } from "./severity";

interface FindingOverlayProps {
  bboxKey: string;
  bbox: BoundingBox;
  findings: VulnerabilityFinding[];
  scale: number;
  pageHeightPt: number;
  isActive: boolean;
  zIndex: number;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement, e: React.MouseEvent) => void;
  focusedFinding?: VulnerabilityFinding | null;
}

export function FindingOverlay({
  bboxKey, bbox, findings, scale, pageHeightPt, isActive, zIndex, onClick, focusedFinding
}: FindingOverlayProps) {
  const rect = pdfToPixels(bbox, pageHeightPt, scale);
  const hasMultiple = findings.length > 1;

  const tone = isActive && focusedFinding ? getTone(focusedFinding) : dominantTone(findings);
  const { rgb, onSolid, label } = TONES[tone];
  const tentative = isActive && focusedFinding
    ? isTentative(focusedFinding)
    : findings.every(isTentative);

  return (
    <div
      aria-label={`${label} finding`}
      className={tone === "major" && !isActive ? "sev-pulse" : undefined}
      onClick={(e) => {
        e.stopPropagation();
        onClick(findings, bboxKey, e.currentTarget, e);
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
        background: `rgb(${rgb} / ${isActive ? 0.28 : 0.14})`,
        borderBottom: `${isActive ? 2.5 : 2}px ${tentative ? "dashed" : "solid"} rgb(${rgb} / ${isActive ? 0.95 : 0.65})`,
        boxShadow: isActive ? `0 0 0 1.5px rgb(${rgb} / 0.4)` : "none",
        transition: "all 150ms ease",
        zIndex,
        "--sev-rgb": rgb,
      } as CSSProperties}
    >
      {hasMultiple && (
        <div
          style={{
            position: "absolute",
            top: -8,
            right: -8,
            background: `rgb(${rgb})`,
            color: onSolid,
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