import { Search, ChevronUp, ChevronDown, X } from "lucide-react";

interface SearchBarProps {
  query: string;
  matchCount: number;
  currentMatch: number;
  onQueryChange: (q: string) => void;
  onNext: () => void;
  onPrev: () => void;
  onClose: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

export function SearchBar({
  query,
  matchCount,
  currentMatch,
  onQueryChange,
  onNext,
  onPrev,
  onClose,
  inputRef,
}: SearchBarProps) {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg border border-border bg-background shadow-sm">
      <Search className="size-3.5 text-muted-foreground shrink-0" />
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.shiftKey ? onPrev() : onNext();
          }
          if (e.key === "Escape") {
            onClose();
          }
        }}
        placeholder="Search in document…"
        className="flex-1 text-xs bg-transparent outline-none placeholder:text-muted-foreground"
      />

      {query && (
        <span className="text-[11px] text-muted-foreground shrink-0 tabular-nums">
          {matchCount === 0 ? "No results" : `${currentMatch + 1} / ${matchCount}`}
        </span>
      )}

      <button
        onClick={onPrev}
        disabled={matchCount === 0}
        className="p-0.5 rounded hover:bg-muted disabled:opacity-30"
        title="Previous (Shift+Enter)"
      >
        <ChevronUp className="size-3.5" />
      </button>

      <button
        onClick={onNext}
        disabled={matchCount === 0}
        className="p-0.5 rounded hover:bg-muted disabled:opacity-30"
        title="Next (Enter)"
      >
        <ChevronDown className="size-3.5" />
      </button>

      <button
        onClick={onClose}
        className="p-0.5 rounded hover:bg-muted"
        title="Close (Esc)"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}