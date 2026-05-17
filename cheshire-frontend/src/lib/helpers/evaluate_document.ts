import type { VulnerabilityFinding } from "../../types/VulnerabilityFinding"
import { authFetch, clearAuth } from "@/lib/auth"
import { PROVIDER } from "@/globals"

export interface EvaluateResponse {
  session_id: string
  vulnerabilities: VulnerabilityFinding[]
}

export interface EvaluateProgressEvent {
  type: "status" | "result" | "error"
  message?: string
  data?: EvaluateResponse
}

export async function evaluateDocument(
  file: File,
  onProgress?: (event: EvaluateProgressEvent) => void
): Promise<EvaluateResponse> {
  const formData = new FormData()
  formData.append("uploaded_document", file)

  const response = await authFetch(
    `/api/v1/evaluate?provider=${PROVIDER}`,
    {
      method: "POST",
      body: formData,
    }
  )

  console.log("Evaluate response:", {
    status: response.status,
    ok: response.ok,
    contentType: response.headers.get("content-type"),
  })

  if (response.status === 401) {
    clearAuth()
    throw new Error("Session expired. Please log in again.")
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText)
    throw new Error(`Evaluation failed: ${detail}`)
  }

  if (!response.body) {
    throw new Error("Server returned no response body.")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()

  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()

      console.log("SSE read:", {
        done,
        bytes: value?.length ?? 0,
      })

      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, "\n")

      const frames = buffer.split("\n\n")
      buffer = frames.pop() ?? ""

      for (const frame of frames) {
        console.log("SSE frame:", frame)

        if (!frame.trim()) continue

        let eventType = "message"
        const dataLines: string[] = []

        for (const line of frame.split("\n")) {
          if (line.startsWith(":")) continue

          if (line.startsWith("event:")) {
            eventType = line.slice("event:".length).trim()
          }

          if (line.startsWith("data:")) {
            dataLines.push(line.slice("data:".length).trim())
          }
        }

        if (dataLines.length === 0) continue

        const dataStr = dataLines.join("\n")

        try {
          const parsed = JSON.parse(dataStr)

          if (eventType === "status") {
            onProgress?.({
              type: "status",
              message: parsed.message,
            })
          }

          if (eventType === "error") {
            onProgress?.({
              type: "error",
              message: parsed.message,
            })

            throw new Error(parsed.message)
          }

          if (eventType === "result") {
            const result = parsed as EvaluateResponse

            onProgress?.({
              type: "result",
              data: result,
            })

            return result
          }
        } catch (err) {
          console.error("Failed to parse SSE frame:", frame, err)

          if (eventType === "error") {
            throw err
          }
        }
      }
    }
  } catch (err) {
    console.error("SSE stream crashed while reading:", err)
    throw err
  }

  throw new Error("SSE stream closed before a result was received.")
}

export async function getSessionResults(sessionId: string): Promise<VulnerabilityFinding[]> {
  return authFetch(`/api/v1/${sessionId}/result`)
    .then(r => (r.ok ? r.json() as Promise<VulnerabilityFinding[]> : []))
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