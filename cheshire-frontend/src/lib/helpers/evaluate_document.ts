import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding"
import { authFetch } from "@/lib/auth"
import { PROVIDER } from "@/globals"

interface EvaluateResponse {
  session_id: string;
  vulnerabilities: VulnerabilityFinding[];
}

/**
 * POST /api/v1/evaluate — uploads a PDF and kicks off an AI audit.
 * Backend identifies the user via the JWT in the Authorization header.
 */
export async function evaluateDocument(file: File): Promise<EvaluateResponse | null> {
  const formData = new FormData()
  formData.append("uploaded_document", file)

  return authFetch(`/api/v1/evaluate?provider=${PROVIDER}`, {
    method: "POST",
    body: formData,
  })
    .then(response => {
      if (!response.ok) {
        throw new Error(`Error evaluating document: ${response.statusText}`)
      }
      return response.json() as Promise<EvaluateResponse>
    })
    .catch(error => {
      console.error("Error evaluating document:", error)
      return null;
    });
}

export async function getSessionResults(sessionId: string): Promise<VulnerabilityFinding[]> {
  return authFetch(`/api/v1/${sessionId}/result`)
    .then(r => r.ok ? r.json() as Promise<VulnerabilityFinding[]> : [])
    .catch(() => [])
}

export async function getSessionDocumentUrl(sessionId: string): Promise<string | null> {
  return authFetch(`/api/v1/${sessionId}/document`)
    .then(r => {
      if (!r.ok) return null
      return r.blob().then(blob => URL.createObjectURL(blob))
    })
    .catch(() => null)
}