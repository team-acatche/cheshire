import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

export function isUnanchored(f: VulnerabilityFinding) {
  const {l, t, r, b} = f.bbox;
  return Math.abs(r - l) === 0 || Math.abs(t - b) === 0;
}

export function categoryOf(f: VulnerabilityFinding) {
  // Missing section: Overview -> "Missing Section"
  return f.title.includes(":") ? f.title.split(":")[0].trim() : "Other";
}

export function shortTitle(f: VulnerabilityFinding) {
  return f.title.includes(":") ? f.title.split(":").slice(1).join(":").trim() : f.title;
}

export function makeBboxKey(f: VulnerabilityFinding) {
  return `${f.page_no}|${f.bbox.l}|${f.bbox.t}|${f.bbox.r}|${f.bbox.b}`;
}

export function groupByBbox(findings: VulnerabilityFinding[], pageNumber: number) {
  const map = new Map<string, VulnerabilityFinding[]>();

  for (const f of findings) {
    if (f.page_no !== pageNumber) continue;
    const key = makeBboxKey(f);
    const group = map.get(key) ?? [];
    group.push(f);
    map.set(key, group);
  }

  return map;
}

export function pdfToPixels(
  bbox: VulnerabilityFinding["bbox"],
  pageHeightPt: number,
  scale: number
) {
  return {
    left: bbox.l * scale,
    top: (pageHeightPt - bbox.t) * scale,
    width: (bbox.r - bbox.l) * scale,
    height: (bbox.t - bbox.b) * scale,
  };
}