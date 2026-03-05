/// This is solely a test component for displaying the findings

import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding";

interface FindingsDisplayProps {
    findings: VulnerabilityFinding[];
}

export function FindingsDisplay({ findings }: FindingsDisplayProps) {
    return (
        <div className="col-span-1 flex flex-col gap-2 p-4 overflow-auto">
            {findings.length === 0 && <p>No findings yet.</p>}
            {findings.map((finding, index) => (
                <details key={index}>
                    <summary className="font-bold">{finding.title}</summary>
                    <p className="text-muted-foreground font-light">(Page {finding.page_no}; @[l:{finding.bbox.l}, t:{finding.bbox.t}, r:{finding.bbox.r}, b:{finding.bbox.b}])</p>
                    <p>{finding.description}</p>
                </details>
            ))}
        </div>
    );
}