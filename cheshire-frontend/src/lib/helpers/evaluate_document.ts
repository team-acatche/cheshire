import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding";

export async function evaluateDocument(root_uri: string, file: File): Promise<VulnerabilityFinding[]> {
    const formData = new FormData();
    formData.append("uploaded_document", file);
    return await fetch(`http://${root_uri}/api/v1/evaluate?provider=together_ai`, {
        method: "POST",
        body: formData,
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Error evaluating document: ${response.statusText}`);
            }
            return response.json() as Promise<VulnerabilityFinding[]>
        })
        .catch(error => {
            console.error("Error evaluating document:", error);
            return [];
        });
}