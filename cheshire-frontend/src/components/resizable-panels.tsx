import { useCallback, useEffect, useRef, useState } from "react"

interface ResizablePanelsProps {
  left: React.ReactNode
  right: React.ReactNode
  defaultLeftPercent?: number
  minLeftPercent?: number
  maxLeftPercent?: number
}

export function ResizablePanels({
  left,
  right,
  defaultLeftPercent = 75,
  minLeftPercent = 25,
  maxLeftPercent = 85,
}: ResizablePanelsProps) {
  const [leftPercent, setLeftPercent] = useState(defaultLeftPercent)
  const containerRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"
  }, [])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const rawPercent = ((e.clientX - rect.left) / rect.width) * 100
      const clamped = Math.min(maxLeftPercent, Math.max(minLeftPercent, rawPercent))
      setLeftPercent(clamped)
    }

    const onMouseUp = () => {
      if (!isDragging.current) return
      isDragging.current = false
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }

    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
    return () => {
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }
  }, [minLeftPercent, maxLeftPercent])

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      {/* Left panel */}
      <div
        className="flex flex-col overflow-hidden"
        style={{ width: `${leftPercent}%`, minWidth: 0 }}
      >
        {left}
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={onMouseDown}
        className="group relative flex w-2 shrink-0 cursor-col-resize items-center justify-center"
      >
        {/* Visual track */}
        <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-ring group-active:bg-ring" />
        {/* Grip dots */}
        <div className="relative z-10 flex flex-col gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {[...Array(5)].map((_, i) => (
            <span
              key={i}
              className="h-1 w-1 rounded-full bg-muted-foreground"
            />
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div
        className="flex flex-col overflow-hidden"
        style={{ width: `${100 - leftPercent}%`, minWidth: 0 }}
      >
        {right}
      </div>
    </div>
  )
}

export default ResizablePanels