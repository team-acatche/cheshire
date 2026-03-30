import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding";
import { USERNAME, PROVIDER } from "@/globals";

interface EvaluateResponse {
    session_id: string;
    vulnerabilities: VulnerabilityFinding[];
}

export async function evaluateDocument(file: File): Promise<EvaluateResponse | null> {
    const formData = new FormData();
    formData.append("uploaded_document", file);

    // TODO: get provider from settings
    // TODO: get username from auth
    return await fetch(`/api/v1/${USERNAME}/evaluate?provider=${PROVIDER}`, {
        method: "POST",
        body: formData,
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Error evaluating document: ${response.statusText}`);
            }
            return response.json() as Promise<EvaluateResponse>
        })
        .catch(error => {
            console.error("Error evaluating document:", error);
            return null;
        });
}

export async function saveResult(session_id: string, file: File) {
    const formData = new FormData();
    formData.append("uploaded_document", file);

    return await fetch(`/api/v1/${USERNAME}/evaluate/${session_id}/result`, {
        method: "POST",
        body: formData,
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Error saving result: ${response.statusText}`);
            }
        })
        .catch(error => {
            console.error("Error saving result:", error);
        });
}