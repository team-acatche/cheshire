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
  major:       { label: "Major",       hint: "Major: Blocks approval. Resolve the issue before approval.",       rank: 3, rgb: "220 38 38",  text: "text-red-600 dark:text-red-400",       onSolid: "#fff",    icon: OctagonAlert },
  minor:       { label: "Minor",       hint: "Minor: Compliance gap. Resolve the issue before development.",  rank: 2, rgb: "234 179 8",  text: "text-yellow-700 dark:text-yellow-400", onSolid: "#422006", icon: TriangleAlert },
  missing:     { label: "Missing",     hint: "Missing: Required content is absent.",       rank: 2, rgb: "249 115 22", text: "text-orange-700 dark:text-orange-400", onSolid: "#431407", icon: FileWarning },
  observation: { label: "Observation", hint: "Observation: Advisory. Resolution is optional, but recommended.",        rank: 1, rgb: "0 51 178",   text: "text-blue-700 dark:text-blue-400",     onSolid: "#fff",    icon: Info },
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
  if (c >= 0.95) return { bars: 3, label: "Confidence Score: 1.0", hint: "evidence for the finding is clear and well-defined" };
  if (c >= 0.75) return { bars: 2, label: "Confidence Score: 0.8",   hint: "clear noncompliance, but the evidence requires some interpretation" };
  return { bars: 1, label: "Confidence Score: 0.6", hint: "Potential noncompliance, but the evidence is unclear or questionable" };
}

export const isTentative = (f: VulnerabilityFinding) => f.confidence != null && f.confidence < 0.75;