import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding"
import { authFetch } from "@/lib/auth"
import { PROVIDER } from "@/globals"

// Types

interface SubmitResponse {
  session_id: string
  status: string
}

interface StatusResponse {
  status: "PENDING" | "RUNNING" | "FAILED"
  error?: string
}

export interface EvaluateResponse {
  session_id: string
  vulnerabilities: VulnerabilityFinding[]
}

export type EvaluationStatus = "PENDING" | "RUNNING" | "FAILED" | "DONE";

// —— Polling config ————————————————————————————————————————————————————————————

function pollInterval(elapsedMs: number): number {
  if (elapsedMs < 60_000) return 3_000 // every 3 s for the first minute
  if (elapsedMs < 180_000) return 8_000 // every 8 s up to 3 minutes
  return 15_000 // every 15 s after that
}

const POLL_TIMEOUT_MS = 40 * 60 * 1_000 // 40 minutes hard stop

// —— Main ——————————————————————————————————————————————————————————————————————
/**
 * POST /api/v1/evaluate — uploads a PDF and kicks off an AI audit.
 * Backend identifies the user via the JWT in the Authorization header.
 */
export async function evaluateDocument(
  file: File,
  onProgress?: (status: EvaluationStatus) => void,
): Promise<EvaluateResponse | null> {

  // 1. Submit - backend returns 202 immediately 
  const formData = new FormData()
  formData.append("uploaded_document", file)

  let session_id: string
  try {
    const res = await authFetch(`/api/v1/evaluate?provider=${PROVIDER}`, {
      method: "POST",
      body: formData,
    })
    if (!res.ok) {
      console.error("evaluate submit network error:", await res.text().catch(() => res.statusText))
      return null
    }
    const data = await res.json() as SubmitResponse
    session_id = data.session_id
  } catch (err) {
    console.error("evaluate submit network error:", err)
    return null
  }

  onProgress?.("PENDING")

  // 2. Poll GET /evaluate/{session_id}/status
  //    - 200 -> still in progress, read body for status at ring
  //    - 301 -> done;  browser/fetch follows to /result automatically
  //                    the final 200 response contains the vulnerability list

  const startedAt = Date.now()
  let lastStatus: EvaluationStatus | null = null

  while (true) {
    const elapsed = Date.now() - startedAt
    if (elapsed > POLL_TIMEOUT_MS) {
      console.error(`evaluate: poll timeout after ${Math.round(elapsed / 1000)}s`)
      return null
    }

    await sleep(pollInterval(elapsed))

    let pollRes: globalThis.Response
    try {
      // redirect: "follow" (default) - fetch will transparently follow the 301
      // and hand us the /result response body directly
      pollRes = await authFetch(`/api/v1/${session_id}/status`)
    } catch (err) {
      console.error("evaluate poll network error:", err)
      return null
    }

    if (!pollRes.ok) {
      console.error("evaluate poll non-OK", pollRes.status)
      return null
    }

    // Detect whether fetch followed a redirect to /result
    // After a 301 -> 200 redirect the URL changes to .../result
    const finalUrl = pollRes.url ?? ""
    if (finalUrl.includes("/result")) {
      onProgress?.("DONE")
      const vulnerabilities = await pollRes.json() as VulnerabilityFinding[]
      return { session_id, vulnerabilities }
    }

    // Still on /status - read the status body
    const body = await pollRes.json() as StatusResponse

    if (body.status === "FAILED") {
      console.error("evaluate job failed:", body.error)
      return null
    }

    if (body.status !== lastStatus) {
      lastStatus = body.status
      onProgress?.(body.status)
    }
  }
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

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}