import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";
 
export interface PageMeta {
  renderedWidth: number;
  renderedHeight: number;
  originalWidth: number;
  originalHeight: number;
}
 
export interface ActiveGroup {
  findings: VulnerabilityFinding[];
  anchorEl: HTMLElement;
  bboxKey: string;
}