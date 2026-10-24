import { useEffect, useState } from "react"
import {
  fetchEvaluationProgress,
  type EvaluationProgress,
  type ProgressEvent,
} from "@/lib/helpers/evaluate_document"

export function useEvaluationProgress(sessionId: string | null, active: boolean) {
  const [progress, setProgress] = useState<EvaluationProgress | null>(null)
  const [events, setEvents] = useState<ProgressEvent[]>([])

  useEffect(() => {
    setProgress(null)
    setEvents([])
    if (!sessionId || !active) return

    let cancelled = false
    let since = 0
    let timer: ReturnType<typeof setTimeout>

    const tick = async () => {
      const p = await fetchEvaluationProgress(sessionId, since)
      if (cancelled) return
      if (p) {
        since = p.last_seq
        setProgress(p)
        if (p.events.length) setEvents((prev) => [...prev, ...p.events].slice(-80))
      }
      timer = setTimeout(tick, p ? 1500 : 4000)
    }
    tick()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [sessionId, active])

  // Progress in the browser tab, visible while you work elsewhere
  useEffect(() => {
    if (!progress || !active) return
    const prev = document.title
    document.title = `(${Math.round(progress.percent)}%) Cheshire`
    return () => { document.title = prev }
  }, [progress, active])

  return { progress: active ? progress : null, events }
}