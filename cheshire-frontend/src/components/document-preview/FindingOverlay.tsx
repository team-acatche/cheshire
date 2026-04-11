import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import { pdfToPixels } from "./helpers";

interface FindingOverlayProps {
  bboxKey: string;
  findings: VulnerabilityFinding[];
  scale: number;
  pageHeightPt: number;
  isActive: boolean;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
}

export function FindingOverlay({
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