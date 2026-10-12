import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

type Box = VulnerabilityFinding["bbox"];

const isEmptyBox = (b: Box) =>
  Math.abs(b.r - b.l) === 0 || Math.abs(b.t - b.b) === 0;

export function getBoxes(f: VulnerabilityFinding): Box[] {
  return f.bboxes?.length ? f.bboxes : [f.bbox];
}
export function isUnanchored(f: VulnerabilityFinding) {
  if (f.scope === "document") return true;
  return getBoxes(f).every(isEmptyBox);
}

export function categoryOf(f: VulnerabilityFinding) {
  // Missing section: Overview -> "Missing Section"
  return f.title.includes(":") ? f.title.split(":")[0].trim() : "Other";
}

export function shortTitle(f: VulnerabilityFinding) {
  return f.title.includes(":") ? f.title.split(":").slice(1).join(":").trim() : f.title;
}

export function makeBboxKey(page: number, b: Box) {
  return `${page}|${b.l}|${b.t}|${b.r}|${b.b}`;
}

export function groupByBbox(findings: VulnerabilityFinding[], pageNumber: number) {
  const map = new Map<string, { bbox: Box; findings: VulnerabilityFinding[] }>();

  for (const f of findings) {
    if (f.page_no !== pageNumber) continue;
    for (const b of getBoxes(f)) {
      if (isEmptyBox(b)) continue;
      const key = makeBboxKey(f.page_no, b);
      const entry = map.get(key) ?? { bbox: b, findings: [] };
      if (!entry.findings.includes(f)) entry.findings.push(f);
      map.set(key, entry);
    }
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