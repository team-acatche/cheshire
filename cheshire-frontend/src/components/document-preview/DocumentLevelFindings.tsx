import { useMemo, useState, forwardRef } from "react";
import { FileWarning, ChevronRight } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
import { categoryOf, shortTitle } from "./helpers";

interface Props {
  findings: VulnerabilityFinding[];
  onSelect: (f: VulnerabilityFinding) => void;
}

export const DocumentLevelFindings = forwardRef<HTMLButtonElement, Props>(
  ({ findings, onSelect }, ref) => {
    const [open, setOpen] = useState(false);

    const groups = useMemo(() => {
      const map = new Map<string, VulnerabilityFinding[]>();
      for (const f of findings) {
        const key = categoryOf(f);
        map.set(key, [...(map.get(key) ?? []), f]);
      }
      return [...map.entries()];
    }, [findings]);

    if (findings.length === 0) return null;

    return (
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            ref={ref}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-background shadow-sm hover:bg-muted transition-colors"
          >
            <FileWarning className="h-3.5 w-3.5 text-blue-500" />
            <span className="text-xs text-muted-foreground">Document-wide</span>
            <span className="text-sm font-semibold">{findings.length}</span>
          </button>
        </PopoverTrigger>

        <PopoverContent className="w-[360px] p-0 gap-0" align="start">
          <div className="px-3 py-2 border-b bg-muted/40">
            <div className="text-sm font-semibold">Document-wide findings</div>
            <div className="text-xs text-muted-foreground">
              Not tied to a specific spot in the PDF
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto py-1">
            {groups.map(([category, items]) => (
              <div key={category} className="mb-1">
                <div className="px-3 py-1 text-[11px] font-semibold uppercase text-muted-foreground">
                  {category} · {items.length}
                </div>
                {items.map((f) => (
                  <button
                    key={f.title}
                    onClick={() => { setOpen(false); onSelect(f); }}
                    className="w-full flex items-center gap-1 px-3 py-1.5 text-left text-sm hover:bg-muted transition-colors"
                  >
                    <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
                    <span className="truncate">{shortTitle(f)}</span>
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