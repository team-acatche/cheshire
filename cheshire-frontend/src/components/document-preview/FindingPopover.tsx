import { useState, useEffect, useMemo } from "react";
import { useFloating, offset, flip, shift, autoUpdate, FloatingPortal } from "@floating-ui/react";
import { ExternalLink, ChevronRight, ChevronLeft, Layers } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import { isUnanchored, getBoxes } from "./helpers";
import { SeverityBadge, ConfidenceMeter } from "./severity-badge";
import { TONES, bySeverity, getTone, isTentative, toneColor } from "./severity";

interface FindingPopoverProps {
  findings: VulnerabilityFinding[];
  anchorEl: HTMLElement;
  onClose: () => void;
  onFocusChange?: (f: VulnerabilityFinding | null) => void;
}

export function FindingPopover({ findings: incoming, anchorEl, onClose, onFocusChange }: FindingPopoverProps) {
  // Most severe first
  const findings = useMemo(() => [...incoming].sort(bySeverity), [incoming]);
  const [page, setPage] = useState(0);
  const finding = findings[page];

  useEffect(() => {
    onFocusChange?.(finding);
  }, [finding, onFocusChange]);

  const recommendations = finding.recommendations ?? [];
  const webReferences = finding.web_references ?? [];
  const total = findings.length;

  const tone = getTone(finding);
  const s = TONES[tone];

  const pages = [...new Set(
    getBoxes(finding).map((b) => b.page_no ?? finding.page_no)
  )].sort((a, b) => a - b);

  const { refs, floatingStyles } = useFloating({
    placement: "bottom-start",
    strategy: "fixed",
    middleware: [
      offset(10),
      flip({ padding: 12, fallbackPlacements: ["top-start", "right-start", "left-start"] }),
      shift({ padding: 12 }),
    ],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(anchorEl);
    setPage(0);
  }, [anchorEl, refs, findings]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const handlePointerDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      const floating = refs.floating.current;
      if (floating && target && !floating.contains(target) && !anchorEl.contains(target)) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousedown", handlePointerDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousedown", handlePointerDown);
    };
  }, [anchorEl, onClose, refs.floating]);

  return (
    <FloatingPortal>
      <div
        ref={refs.setFloating}
        style={{ ...floatingStyles, zIndex: 9999, borderColor: toneColor(tone, 0.35) }}
        className="
          w-80 rounded-xl border bg-white shadow-xl
          ring-1 ring-black/5 overflow-hidden
          dark:bg-zinc-900
          origin-top-left
          animate-in fade-in-0 zoom-in-95 slide-in-from-top-2
          duration-300
        "
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="px-4 py-3 border-b"
          style={{ background: toneColor(tone, 0.08), borderColor: toneColor(tone, 0.2) }}
        >
          <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <SeverityBadge tone={tone} />
            {tone === "missing" && finding.severity && (
              <span className="text-[10px] capitalize text-zinc-500 dark:text-zinc-400">
                {finding.severity} priority
              </span>
            )}
            <ConfidenceMeter value={finding.confidence} />
            <Badge variant="outline" className="ml-auto shrink-0 text-[10px]">
              {isUnanchored(finding) ? "Document" : `pg. ${pages.join(", ")}`}
            </Badge>
          </div>

          <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug">
            {finding.title}
          </p>

          {total > 1 && (
            <div
              className="flex items-center justify-between mt-2 pt-2 border-t"
              style={{ borderColor: toneColor(tone, 0.15) }}
            >
              <div className={`flex items-center gap-1 text-[11px] font-medium ${s.text}`}>
                <Layers className="size-3" />
                <span>{page + 1} of {total} findings</span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Previous finding"
                >
                  <ChevronLeft className={`size-3.5 ${s.text}`} />
                </button>

                {/* One dot per finding, each in its own severity color */}
                <div className="flex gap-0.5">
                  {findings.map((f, i) => (
                    <button
                      key={i}
                      onClick={() => setPage(i)}
                      className={`rounded-full transition-all ${i === page ? "w-3 h-1.5" : "w-1.5 h-1.5"}`}
                      style={{ background: toneColor(getTone(f), i === page ? 1 : 0.45) }}
                      aria-label={`Go to finding ${i + 1}`}
                    />
                  ))}
                </div>

                <button
                  onClick={() => setPage((p) => Math.min(total - 1, p + 1))}
                  disabled={page === total - 1}
                  className="p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Next finding"
                >
                  <ChevronRight className={`size-3.5 ${s.text}`} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-4 py-3 space-y-3 max-h-72 overflow-y-auto">
          <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed">
            {finding.description}
          </p>

          {isTentative(finding) && (
            <p className="text-[11px] italic text-zinc-500 dark:text-zinc-400">
              Lower confidence: inferred from context. Double-check this against the source.
            </p>
          )}

          { recommendations.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1.5">
                Recommendations
              </p>
              <ul className="space-y-1.5">
                {recommendations.map((rec, i) => (
                  <li key={i} className="flex gap-2 text-xs text-zinc-700 dark:text-zinc-300 leading-snug">
                    <ChevronRight className={`size-3 mt-0.5 shrink-0 ${s.text}`} />
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}


          {webReferences.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1.5">
                References
              </p>
              <ul className="space-y-1">
                {webReferences.map((url, i) => (
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