import { useState, useEffect } from "react";
import {
  useFloating,
  offset,
  flip,
  shift,
  autoUpdate,
  FloatingPortal,
} from "@floating-ui/react";
import {
  ExternalLink,
  ChevronRight,
  ChevronLeft,
  Layers,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

interface FindingPopoverProps {
  findings: VulnerabilityFinding[];
  anchorEl: HTMLElement;
  onClose: () => void;
}

export function FindingPopover({ findings, anchorEl, onClose }: FindingPopoverProps) {
  const [page, setPage] = useState(0);
  const finding = findings[page];
  const total = findings.length;

  const { refs, floatingStyles } = useFloating({
    placement: "bottom-start",
    strategy: "fixed",
    middleware: [
      offset(10),
      flip({
        padding: 12,
        fallbackPlacements: ["top-start", "right-start", "left-start"],
      }),
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

      if (
        floating &&
        target &&
        !floating.contains(target) &&
        !anchorEl.contains(target)
      ) {
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
        style={{ ...floatingStyles, zIndex: 9999 }}
        className="
          w-80 rounded-xl border border-blue-200/60 bg-white shadow-xl
          ring-1 ring-black/5 overflow-hidden
          dark:bg-zinc-900 dark:border-blue-400/20
          origin-top-left
          animate-in fade-in-0 zoom-in-95 slide-in-from-top-2
          duration-300
        "
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-blue-50 dark:bg-blue-950/40 px-4 py-3 border-b border-blue-100/80 dark:border-blue-400/15">
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug flex-1">
              {finding.title}
            </p>

            <Badge
              variant="outline"
              className="shrink-0 text-[10px] border-blue-300 text-blue-700 dark:text-blue-400 dark:border-blue-600"
            >
              pg. {finding.page_no}
            </Badge>
          </div>

          {total > 1 && (
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-blue-100/60 dark:border-blue-400/10">
              <div className="flex items-center gap-1 text-[11px] text-blue-700 dark:text-blue-400 font-medium">
                <Layers className="size-3" />
                <span>
                  {page + 1} of {total} findings
                </span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="p-0.5 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Previous finding"
                >
                  <ChevronLeft className="size-3.5 text-blue-700 dark:text-blue-400" />
                </button>

                <div className="flex gap-0.5">
                  {findings.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setPage(i)}
                      className={`rounded-full transition-all ${
                        i === page
                          ? "w-3 h-1.5 bg-blue-500"
                          : "w-1.5 h-1.5 bg-blue-300 hover:bg-blue-400"
                      }`}
                      aria-label={`Go to finding ${i + 1}`}
                    />
                  ))}
                </div>

                <button
                  onClick={() => setPage((p) => Math.min(total - 1, p + 1))}
                  disabled={page === total - 1}
                  className="p-0.5 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  aria-label="Next finding"
                >
                  <ChevronRight className="size-3.5 text-blue-700 dark:text-blue-400" />
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

          {finding.recommendations.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide mb-1.5">
                Recommendations
              </p>
              <ul className="space-y-1.5">
                {finding.recommendations.map((rec, i) => (
                  <li
                    key={i}
                    className="flex gap-2 text-xs text-zinc-700 dark:text-zinc-300 leading-snug"
                  >
                    <ChevronRight className="size-3 mt-0.5 shrink-0 text-blue-500" />
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