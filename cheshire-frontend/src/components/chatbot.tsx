// src/components/chatbot.tsx
import { useState, useRef, useEffect, type KeyboardEvent, type ReactNode } from "react"
import { Card } from "./ui/card"
import { Textarea } from "./ui/textarea"
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

export function Chatbot({ findings, sessionId, profileImage, onActivity, }: ChatbotProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState<string>("")
  const [typing, setTyping] = useState<boolean>(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  // Load history when session changes
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
                ) {
                  return null
                }

                return {
                  role: msg._role as "user" | "bot1" | "bot2" | "bot3",
                  text,
                }
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

  const sendMessage = async () => {
    if (!input.trim()) return

    const userText = input
    setMessages(prev => [...prev, { role: "user", text: userText }])
    setInput("")
    setTyping(true)

    // This moves chat to top immediately on user activity
    onActivity?.()

    try {
      const response = await authFetch(
        `/api/v1/${sessionId}?evaluation_mode=${EVALUATION_MODE}&provider=${PROVIDER}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: userText }),
        }
      )

      if (!response.ok) throw new Error("Failed to send message")

      const data = await response.json()
      const message = data.response as ResponseMessage
      setMessages(prev => [
        ...prev,
        {
          role: "bot1",
          text: message._content
            .filter(c => c.text)
            .map(c => c.text)
            .join("\n\n"),
        },
      ])

      onActivity?.()
    } catch {
      setMessages(prev => [
        ...prev,
        { role: "bot1", text: "Sorry, I encountered an error. Please try again." },
      ])
    } finally {
      setTyping(false)
    }
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

  return (
    <Card className="h-full w-full min-w-0 flex flex-col overflow-hidden rounded-none pt-6 pb-0 shadow-sm">

      {/* Chat area */}
      <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4 text-sm scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <div className="flex flex-col gap-6">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex items-start gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role !== "user" && (
                <div className="w-8 h-8 overflow-hidden shrink-0">
                  <img src="/cheshire-black.png" className="w-full h-full object-cover dark:invert" alt="agent" />
                </div>
              )}

              <div
                className={
                  msg.role === "user"
                    ? "btn-gradient max-w-[80%] px-3 py-2 rounded-2xl rounded-br-sm text-white text-sm [&_p]:text-white [&_li]:text-white [&_ol]:text-white [&_ul]:text-white [&_blockquote]:text-white [&_td]:text-white [&_th]:text-white [&_a]:text-white/90"
                    : "w-full min-w-0 overflow-hidden px-4 text-foreground wrap-break-word"
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
                      <div className="w-full max-w-187.5 min-w-0 space-y-4 overflow-hidden wrap-break-word">
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
            <div className="flex justify-start">
              <div className="bg-muted px-3 py-2 rounded-2xl rounded-bl-sm flex gap-1">
                <span className="animate-bounce text-muted-foreground">.</span>
                <span className="animate-bounce delay-100 text-muted-foreground">.</span>
                <span className="animate-bounce delay-200 text-muted-foreground">.</span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-border p-4 flex flex-col gap-2 bg-card">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What would you like to know?"
          className="resize-none border-none focus-visible:ring-0 p-0 text-base min-h-10 bg-transparent text-foreground placeholder:text-muted-foreground"
        />

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <UploadSimpleIcon size={22} color="currentColor" />
            <Select>
              <SelectTrigger className="border-none shadow-none focus:ring-0 h-auto p-0 gap-1 font-medium text-muted-foreground">
                <SelectValue placeholder="Agent 1" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Agent 1">Agent 1</SelectItem>
                <SelectItem value="Agent 2">Agent 2</SelectItem>
                <SelectItem value="Agent 3">Agent 3</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <button
            onClick={sendMessage}
            className="bg-muted hover:bg-muted/70 text-muted-foreground p-2 rounded-full transition-colors"
          >
            <SentIcon size={22} color="currentColor" />
          </button>
        </div>
      </div>
    </Card>
  )
}