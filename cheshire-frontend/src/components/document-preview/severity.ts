import { OctagonAlert, TriangleAlert, Info, FileWarning, type LucideIcon } from "lucide-react";
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

export type Tone = "major" | "minor" | "observation" | "missing";

export interface ToneStyle {
  label: string;
  hint: string;
  rank: number;
  rgb: string;
  text: string;
  onSolid: string; 
  icon: LucideIcon;
}

export const TONES: Record<Tone, ToneStyle> = {
  major:       { label: "Major",       hint: "Blocks approval, fix first",       rank: 3, rgb: "220 38 38",  text: "text-red-600 dark:text-red-400",       onSolid: "#fff",    icon: OctagonAlert },
  minor:       { label: "Minor",       hint: "Compliance gap, should be fixed",  rank: 2, rgb: "234 179 8",  text: "text-yellow-700 dark:text-yellow-400", onSolid: "#422006", icon: TriangleAlert },
  missing:     { label: "Missing",     hint: "Required content is absent",       rank: 2, rgb: "234 179 8",  text: "text-yellow-700 dark:text-yellow-400", onSolid: "#422006", icon: FileWarning },
  observation: { label: "Observation", hint: "Advisory, nice to improve",        rank: 1, rgb: "0 51 178",   text: "text-blue-700 dark:text-blue-400",     onSolid: "#fff",    icon: Info },
};

export const TONE_ORDER: Tone[] = ["major", "minor", "observation", "missing"];

export const toneColor = (tone: Tone, alpha = 1) => `rgb(${TONES[tone].rgb} / ${alpha})`;

/** Missing = document-level findings (no PDF location) or titles like "Missing Section: ..." */
export function getTone(f: VulnerabilityFinding): Tone {
  if (f.scope === "document" || /^missing\b/i.test(f.title)) return "missing";
  return f.severity ?? "observation";
}

export const bySeverity = (a: VulnerabilityFinding, b: VulnerabilityFinding) =>
  TONES[getTone(b)].rank - TONES[getTone(a)].rank;

export function dominantTone(findings: VulnerabilityFinding[]): Tone {
  return findings.reduce<Tone>((best, f) => {
    const t = getTone(f);
    return TONES[t].rank > TONES[best].rank ? t : best;
  }, "observation");
}

export function countByTone(findings: VulnerabilityFinding[]): Record<Tone, number> {
  const c: Record<Tone, number> = { major: 0, minor: 0, observation: 0, missing: 0 };
  for (const f of findings) c[getTone(f)]++;
  return c;
}

export interface ConfidenceLevel { bars: 1 | 2 | 3; label: string; hint: string }

export function confidenceLevel(c?: number | null): ConfidenceLevel | null {
  if (c == null) return null;
  if (c >= 0.95) return { bars: 3, label: "Verified", hint: "directly observed in the document" };
  if (c >= 0.75) return { bars: 2, label: "Likely",   hint: "clear textual or visual evidence" };
  return { bars: 1, label: "Possible", hint: "inferred from context, double-check it" };
}

export const isTentative = (f: VulnerabilityFinding) => f.confidence != null && f.confidence < 0.75;