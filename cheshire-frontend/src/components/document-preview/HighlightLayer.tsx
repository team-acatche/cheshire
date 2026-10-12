import { useMemo, useRef } from "react";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import type { PageMeta } from "./types";
import { groupByBbox, pdfToPixels } from "./helpers";
import { FindingOverlay } from "./FindingOverlay";

const KEY_SEP = "::";

interface HighlightLayerProps {
  pageNumber: number;
  pageMeta: PageMeta;
  findings: VulnerabilityFinding[];
  activeBboxKey: string | null;
  onClick: (group: VulnerabilityFinding[], bboxKey: string, el: HTMLElement) => void;
}

export function HighlightLayer({
  pageNumber, pageMeta, findings, activeBboxKey, onClick,
}: HighlightLayerProps) {
  const layerRef = useRef<HTMLDivElement>(null);
  const scale = pageMeta.renderedWidth / pageMeta.originalWidth;

  // Largest first → smallest rendered last → smallest ends up on top
  const entries = useMemo(() => {
    const groups = groupByBbox(findings, pageNumber);
    return Array.from(groups.entries())
      .map(([key, group]) => {
        const rect = pdfToPixels(group[0].bbox, pageMeta.originalHeight, scale);
        return { key, group, rect, area: rect.width * rect.height };
      })
      .sort((a, b) => b.area - a.area);
  }, [findings, pageNumber, pageMeta.originalHeight, scale]);

  if (entries.length === 0) return null;

  const activeKeys = activeBboxKey ? activeBboxKey.split(KEY_SEP) : [];

  const handleClick = (
    group: VulnerabilityFinding[],
    key: string,
    el: HTMLElement,
    e: React.MouseEvent
  ) => {
    const layer = layerRef.current?.getBoundingClientRect();
    if (!layer) return onClick(group, key, el);

    const x = e.clientX - layer.left;
    const y = e.clientY - layer.top;

    // every overlay under the click point, smallest (most specific) first
    const hits = entries
      .filter(({ rect }) =>
        x >= rect.left && x <= rect.left + rect.width &&
        y >= rect.top  && y <= rect.top + rect.height
      )
      .sort((a, b) => a.area - b.area);

    if (hits.length <= 1) return onClick(group, key, el);

    onClick(
      hits.flatMap((h) => h.group),
      hits.map((h) => h.key).join(KEY_SEP),
      el
    );
  };

  return (
    <div
      ref={layerRef}
      style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 5 }}
    >
      {entries.map(({ key, group }, i) => (
        <FindingOverlay
          key={key}
          bboxKey={key}
          findings={group}
          scale={scale}
          pageHeightPt={pageMeta.originalHeight}
          isActive={activeKeys.includes(key)}
          zIndex={20 + i}
          onClick={handleClick}
        />
      ))}
    </div>
  );
}