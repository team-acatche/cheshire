import { useMemo, useState, forwardRef } from "react";
import { FileWarning, ChevronRight } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import { categoryOf, shortTitle } from "./helpers";
import { TONES, bySeverity, dominantTone, getTone, toneColor } from "./severity";

interface Props {
  findings: VulnerabilityFinding[];
  onSelect: (f: VulnerabilityFinding) => void;
  container?: HTMLElement | null;
}

export const DocumentLevelFindings = forwardRef<HTMLButtonElement, Props>(
  ({ findings, onSelect, container }, ref) => {
    const [open, setOpen] = useState(false);

    // Sorted worst-first, so groups are ordered by their most severe member
    const groups = useMemo(() => {
      const map = new Map<string, VulnerabilityFinding[]>();
      for (const f of [...findings].sort(bySeverity)) {
        const key = categoryOf(f);
        map.set(key, [...(map.get(key) ?? []), f]);
      }
      return [...map.entries()];
    }, [findings]);

    if (findings.length === 0) return null;

    const tone = dominantTone(findings);

    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            ref={ref}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm hover:bg-muted transition-colors"
            style={{ borderColor: toneColor(tone, 0.5) }}
          >
            <FileWarning className={`h-3.5 w-3.5 ${TONES[tone].text}`} />
            <span className="text-xs text-muted-foreground">Document-wide</span>
            <span className="text-sm font-semibold">{findings.length}</span>
          </button>
        </PopoverTrigger>

        <PopoverContent container={container} className="w-90 p-0 gap-0" align="start">
          <div className="px-3 py-2 border-b bg-muted/40">
            <div className="text-sm font-semibold">Document-wide findings</div>
            <div className="text-xs text-muted-foreground">Not tied to a specific spot in the PDF</div>
          </div>
          <div className="max-h-80 overflow-y-auto py-1 scroll-transparent">
            {groups.map(([category, items]) => (
              <div key={category} className="mb-1">
                <div className="px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground">
                  {category} · {items.length}
                </div>
                {items.map((f) => (
                  <button
                    key={f.title}
                    onClick={() => { setOpen(false); onSelect(f); }}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted transition-colors"
                  >
                    <span
                      className="size-2 shrink-0 rounded-full"
                      style={{ background: toneColor(getTone(f)) }}
                    />
                    <span className="truncate">{shortTitle(f)}</span>
                    <ChevronRight className="ml-auto size-3 shrink-0 text-muted-foreground" />
                  </button>
                ))}
              </div>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    );
  }
);