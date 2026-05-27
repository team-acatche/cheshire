import { useState, useRef, useEffect, type KeyboardEvent, type ReactNode } from "react"
import { Card } from "./ui/card"
import TextareaAutosize from "react-textarea-autosize"
import UploadSimpleIcon from "./ui/upload-icon"
import {
  Select,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectItem,
} from "./ui/select"
import SentIcon from "./ui/sent-icon"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkBreaks from "remark-breaks"
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import CodeBlock from "@/components/code-block"
import VulnerabilityFindingComponent from "./vulnerability-finding"
import type { ResponseMessages, ResponseMessage } from "@/lib/chat"
import { EVALUATION_MODE, PROVIDER } from "@/globals"
import { authFetch } from "@/lib/auth"

type Message = {
  role: "user" | "bot1" | "bot2" | "bot3"
  text: string
}

interface ChatbotProps {
  findings: VulnerabilityFinding[]
  sessionId: string
  username: string
  profileImage?: string
  onOpenSettings: () => void
  onActivity?: () => void
}

export function Chatbot({ findings, sessionId, profileImage, onActivity }: ChatbotProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState<string>("")
  const [typing, setTyping] = useState<boolean>(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const lastEventIdRef = useRef<string | null>(null)

  // ── Load history on session change ────────────────────────────────────────
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await authFetch(`/api/v1/${sessionId}`)
        if (!response.ok) throw new Error("Failed to fetch history")

        const data = await response.json() as ResponseMessages
        const backendMessages = data.messages ?? []

        if (backendMessages.length > 0) {
          setMessages(
            backendMessages
              .map((msg: ResponseMessage): Message | null => {
                const text = msg._content.map(c => c.text ?? "").join("\n\n").trim()

                if (
                  text.startsWith("Tool:") ||
                  text.startsWith("Arguments:") ||
                  text === "" ||
                  msg._role === "system"
                ) return null
                return { role: msg._role as "user" | "bot1" | "bot2" | "bot3", text }
              })
              .filter((m): m is Message => m !== null)
          )
        } else {
          setMessages([
            { role: "bot1", text: "Hello! I'm your security audit assistant." },
            { role: "bot1", text: "I've evaluated the document and found the following vulnerabilities:" },
            ...findings.map((f): Message => ({ role: "bot1", text: JSON.stringify(f) })),
            { role: "bot1", text: "How can I help you?" },
          ])
        }
      } catch {
        setMessages([{ role: "bot1", text: "Hello! I'm ready to help you with the document." }])
      }
    }
    fetchHistory()
  }, [sessionId, findings])

  // ── Message update helpers ────────────────────────────────────────────────
  const appendToLastBotMessage = (text: string) => {
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (!last || last.role !== "bot1") {
        updated.push({ role: "bot1", text })
      } else {
        updated[updated.length - 1] = { ...last, text: last.text + text }
      }
      return updated
    })
  }

  const replaceLastBotMessage = (text: string) => {
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (!last || last.role !== "bot1") {
        updated.push({ role: "bot1", text })
      } else {
        updated[updated.length - 1] = { ...last, text }
      }
      return updated
    })
  }

  // ── SSE frame parser ──────────────────────────────────────────────────────
  const processFrame = (frame: string) => {
    if (!frame.trim()) return

    const lines = frame.split("\n")
    let eventType = ""
    const dataLines: string[] = []
    let eventId = ""

    for (const line of lines) {
      if (line.startsWith(":")) {
        // SSE comment — keepalive ping, ignore silently
        return
      } else if (line.startsWith("event:")) {
        eventType = line.slice("event:".length).trim()
      } else if (line.startsWith("data:")) {
        // Collect data lines separately — do NOT concat with +=
        // to avoid merging multi-line data without a separator
        dataLines.push(line.slice("data:".length).trim())
      } else if (line.startsWith("id:")) {
        eventId = line.slice("id:".length).trim()
      }
    }

    if (eventId) lastEventIdRef.current = eventId
    if (!eventType || dataLines.length === 0) return

    const dataStr = dataLines.join("\n")

    try {
      const parsed = JSON.parse(dataStr)

      if (eventType === "token" && parsed.content) {
        appendToLastBotMessage(parsed.content)
      } else if (eventType === "done") {
        if (parsed.content) replaceLastBotMessage(parsed.content)
        lastEventIdRef.current = null
        onActivity?.()
      } else if (eventType === "error") {
        replaceLastBotMessage(`Error: ${parsed.message ?? "Unknown error"}`)
      }
    } catch (err) {
      console.error("Failed to parse SSE frame:", frame, err)
    }
  }

  // ── SSE consumer ──────────────────────────────────────────────────────────
  const consumeSSE = async (userText: string, lastEventId: string | null): Promise<void> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    }
    if (lastEventId !== null) headers["Last-Event-ID"] = lastEventId

    const response = await authFetch(
      `/api/v1/${sessionId}?evaluation_mode=${EVALUATION_MODE}&provider=${PROVIDER}`,
      { method: "POST", headers, body: JSON.stringify({ message: userText }) }
    )

    if (!response.ok) throw new Error("Failed to send message")
    if (!response.body) throw new Error("No response body")

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()

      if (value) {
        buffer += decoder.decode(value, { stream: true })
        // Normalise line endings
        buffer = buffer.replace(/\r\n/g, "\n")

        const frames = buffer.split("\n\n")
        // Keep the last (possibly partial) frame in the buffer
        buffer = frames.pop() ?? ""

        for (const frame of frames) {
          processFrame(frame)
        }
      }

      if (done) {
        // Flush any remaining bytes in the buffer
        const remaining = buffer.trim()
        if (remaining) processFrame(remaining)
        break
      }
    }
  }

  // ── Send message with retry ───────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || typing) return

    const userText = input
    setMessages(prev => [...prev, { role: "user", text: userText }])
    setInput("")
    setTyping(true)
    // Append placeholder bot message that tokens stream into
    setMessages(prev => [...prev, { role: "bot1", text: "" }])
    onActivity?.()

    const MAX_RETRIES = 2
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        await consumeSSE(userText, lastEventIdRef.current)
        break // success
      } catch {
        if (attempt === MAX_RETRIES) {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.role === "bot1" && last.text === "") {
              updated[updated.length - 1] = { ...last, text: "Sorry, I encountered an error. Please try again." }
            } else {
              updated.push({ role: "bot1", text: "Sorry, I encountered an error. Please try again." })
            }
            return updated
          })
        } else {
          // Exponential backoff before retry
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
        }
      }
    }

    lastEventIdRef.current = null
    setTyping(false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, typing])

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Card className="h-full w-full min-w-0 flex flex-col overflow-hidden rounded-none pt-6 pb-0 shadow-sm">

      {/* Chat area */}
      <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4 text-sm scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <div className="flex flex-col gap-8 max-w-4xl mx-auto w-full">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`
                flex items-start gap-4
                animate-in fade-in slide-in-from-bottom-2 duration-300
                ${msg.role === "user" ? "justify-end" : "justify-start"}
              `}
            >
              {msg.role !== "user" && (
                <div className="w-8 h-8 mt-1 overflow-hidden shrink-0 opacity-80">
                  <img src="/cheshire-black.png" className="w-full h-full object-cover dark:invert" alt="agent" />
                </div>
              )}

              <div
                className={
                  msg.role === "user"
                    ? "btn-gradient max-w-[80%] px-4 py-3 rounded-2xl rounded-br-sm text-white text-sm shadow-sm transition-all duration-200 [&_p]:text-white [&_li]:text-white [&_ol]:text-white [&_ul]:text-white [&_blockquote]:text-white [&_td]:text-white [&_th]:text-white [&_a]:text-white/90"
                    : "flex-1 min-w-0 overflow-hidden text-foreground"
                }
              >
                {(() => {
                  try {
                    return <VulnerabilityFindingComponent finding={JSON.parse(msg.text) as VulnerabilityFinding} />
                  } catch {
                    const content = (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkBreaks]}
                        components={{
                          table: ({ children }: { children?: ReactNode }) => (
                            <div className="my-4 overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
                              <table className="w-full border-collapse text-sm">
                                {children}
                              </table>
                            </div>
                          ),
                          thead: ({ children }: { children?: ReactNode }) => (
                            <thead className="bg-muted text-muted-foreground">
                              {children}
                            </thead>
                          ),
                          th: ({ children }: { children?: ReactNode }) => (
                            <th className="border border-border px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide">
                              {children}
                            </th>
                          ),
                          td: ({ children }: { children?: ReactNode }) => (
                            <td className="border border-border px-4 py-2 text-sm align-top">
                              {children}
                            </td>
                          ),
                          tr: ({ children }: { children?: ReactNode }) => (
                            <tr className="hover:bg-muted/50">
                              {children}
                            </tr>
                          ),
                          p: ({ children }: { children?: ReactNode }) => (
                            <p className="mb-3 text-[15px] leading-7 text-foreground">
                              {children}
                            </p>
                          ),
                          ul: ({ children }: { children?: ReactNode }) => (
                            <ul className="my-3 list-disc space-y-1 pl-6 text-foreground">
                              {children}
                            </ul>
                          ),
                          ol: ({ children }: { children?: ReactNode }) => (
                            <ol className="my-3 list-decimal space-y-1 pl-6 text-foreground">
                              {children}
                            </ol>
                          ),
                          li: ({ children }: { children?: ReactNode }) => (
                            <li className="mb-1 wrap-break-word text-foreground">{children}</li>
                          ),
                          blockquote: ({ children }: { children?: ReactNode }) => (
                            <blockquote className="my-2 border-l-4 border-border pl-4 italic text-muted-foreground">
                              {children}
                            </blockquote>
                          ),
                          hr: () => (
                            <div className="my-8 flex items-center">
                              <div className="flex-1 border-t border-border" />
                            </div>
                          ),
                          pre: ({ children }: { children?: ReactNode }) => {
                            const codeElement = children as any
                            const code = codeElement?.props?.children || ""
                            const className = codeElement?.props?.className || ""
                            const match = /language-(\w+)/.exec(className || "")
                            const language = match ? match[1] : "text"
                            return <CodeBlock language={language}>{code}</CodeBlock>
                          },
                        }}
                      >
                        {msg.text}
                      </ReactMarkdown>
                    )
                    return msg.role === "user" ? content : (
                      <div className="prose prose-neutral dark:prose-invert max-w-none min-w-0 overflow-hidden break-words">
                        {content}
                      </div>
                    )
                  }
                })()}
              </div>

              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-full overflow-hidden shrink-0 ring-1 ring-border">
                  <img
                    src={profileImage || "/User.png"}
                    onError={(e) => { e.currentTarget.src = "/User.png" }}
                    className="w-full h-full object-cover"
                    alt="user"
                  />
                </div>
              )}
            </div>
          ))}

          {typing && (
            <div className="flex items-start gap-3 animate-in fade-in duration-300">
              <div className="w-6 h-6 mt-1 overflow-hidden shrink-0 opacity-80">
                <img
                  src="/cheshire-black.png"
                  className="w-full h-full object-cover dark:invert"
                  alt="agent"
                />
              </div>

              <div className="flex items-center gap-1 pt-1.5">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="sticky bottom-0 z-10 bg-gradient-to-t from-background via-background/95 to-transparent px-4 pb-4 pt-6">
        <div className="mx-auto max-w-4xl">

          <div
            className="
              relative
              flex items-end gap-3
              rounded-[28px]
              border border-border/60
              bg-background/80
              px-5 py-4
              shadow-[0_8px_30px_rgba(0,0,0,0.06)]
              backdrop-blur-xl
              transition-all duration-200
              focus-within:border-border
              focus-within:shadow-[0_12px_40px_rgba(0,0,0,0.10)]
            "
          >

            {/* soft inner glow */}
            <div className="pointer-events-none absolute inset-0 rounded-[28px] ring-1 ring-white/5" />

            <TextareaAutosize
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What would you like to know?"
              disabled={typing}
              minRows={1}
              maxRows={8}
              className="
                max-h-52
                flex-1
                resize-none
                border-0
                bg-transparent
                p-0
                text-[15px]
                leading-7
                text-foreground
                shadow-none
                outline-none
                focus:outline-none
                focus-visible:ring-0
                disabled:opacity-50
                placeholder:text-muted-foreground/70
              "
            />

            <button
              onClick={sendMessage}
              disabled={typing || !input.trim()}
              className="
                flex h-10 w-10 shrink-0 items-center justify-center
                rounded-full
                bg-muted
                text-muted-foreground
                transition-all duration-200

                hover:scale-105
                hover:bg-muted/80

                active:scale-95

                disabled:scale-100
                disabled:cursor-not-allowed
                disabled:opacity-50
              "
            >
              <SentIcon size={18} color="currentColor" />
            </button>
          </div>

          <p className="mt-2 text-center text-xs text-muted-foreground/60">
            Cheshire can make mistakes. Verify important security findings.
          </p>
        </div>
</div>
    </Card>
  )
}