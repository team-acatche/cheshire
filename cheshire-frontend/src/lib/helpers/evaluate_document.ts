import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding"
import { authFetch } from "@/lib/auth"
import { PROVIDER } from "@/globals"

// ── Types ─────────────────────────────────────────────────────────────────────

interface SubmitResponse {
  session_id: string
  status: string
}

interface StatusResponse {
  status: "PENDING" | "RUNNING" | "PROCESSING" |"FAILED"
  error?: string
}

export interface EvaluateResponse {
  session_id: string
  vulnerabilities: VulnerabilityFinding[]
}

export type EvaluationStatus = "PENDING" | "RUNNING" | "PROCESSING" | "FAILED" | "DONE"

// ── Polling config ────────────────────────────────────────────────────────────

function pollInterval(elapsedMs: number): number {
  if (elapsedMs < 60_000)  return 3_000
  if (elapsedMs < 180_000) return 8_000
  return 15_000
}

const POLL_TIMEOUT_MS = 40 * 60 * 1_000

// ── Submit only ───────────────────────────────────────────────────────────────
// This will be called first to get the session_id immediately so the sidebar can show it.

export async function submitEvaluation(file: File): Promise<string | null> {
  const formData = new FormData()
  formData.append("uploaded_document", file)

  try {
    const res = await authFetch(`/api/v1/evaluate?provider=${PROVIDER}`, {
      method: "POST",
      body: formData,
    })
    if (!res.ok) {
      console.error("evaluate submit error:", await res.text().catch(() => res.statusText))
      return null
    }
    const data = (await res.json()) as SubmitResponse
    return data.session_id
  } catch (err) {
    console.error("evaluate submit network error:", err)
    return null
  }
}

// ── Poll until done ───────────────────────────────────────────────────────────
// This will be called after submitEvaluation() with the returned session_id.

export async function pollEvaluation(
  session_id: string,
  onProgress?: (status: EvaluationStatus) => void,
): Promise<EvaluateResponse | null> {
  onProgress?.("PENDING")

  const startedAt = Date.now()

  while (true) {
    const elapsed = Date.now() - startedAt
    if (elapsed > POLL_TIMEOUT_MS) {
      console.error(`evaluate: poll timeout after ${Math.round(elapsed / 1000)}s`)
      return null
    }

    await sleep(pollInterval(elapsed))

    let pollRes: globalThis.Response
    try {
      pollRes = await authFetch(`/api/v1/${session_id}/status`, { redirect: "follow"})
    } catch (err) {
      console.error("evaluate poll network error:", err)
      return null
    }

    if (!pollRes.ok) {
      console.error("evaluate poll non-OK:", pollRes.status)
      return null
    }

    // fetch follows the 301 automatically — detect by checking the final URL
    const finalUrl = pollRes.url ?? ""
    if (finalUrl.includes("/result")) {
      onProgress?.("DONE")
      const vulnerabilities = await pollRes.json() as VulnerabilityFinding[]
      return { session_id, vulnerabilities }
    }

    // Still in progress
    const body = await pollRes.json() as StatusResponse
    if (body.status === "FAILED") {
      console.error("evaluate job failed:", body.error)
      return null
    }

    onProgress?.(body.status as EvaluationStatus)
  }
}

// ── Combined helper (backwards compat) ────────────────────────────────────────

export async function evaluateDocument(
  file: File,
  onProgress?: (status: EvaluationStatus) => void,
): Promise<EvaluateResponse | null> {
  const session_id = await submitEvaluation(file)
  if (!session_id) return null
  return pollEvaluation(session_id, onProgress)
}


export async function getSessionResults(sessionId: string): Promise<VulnerabilityFinding[]> {
  return authFetch(`/api/v1/${sessionId}/result`)
    .then(r => (r.ok ? r.json() as Promise<VulnerabilityFinding[]> : []))
    .catch(() => [])
}

export async function getSessionDocumentUrl(sessionId: string): Promise<string | null> {
  return authFetch(`/api/v1/${sessionId}/document`)
    .then(r => r.ok ? r.blob().then(b => URL.createObjectURL(b)) : null)
    .catch(() => null)
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}