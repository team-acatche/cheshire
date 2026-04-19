// src/components/chatbot.tsx
import { useState, useRef, useEffect, type KeyboardEvent } from "react"
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
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
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
  username: string   // kept for avatar display; auth is now JWT-based
}

export function Chatbot({ findings, sessionId }: ChatbotProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput]       = useState<string>("")
  const [typing, setTyping]     = useState<boolean>(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  // Load history when session changes
  useEffect(() => {
    const fetchHistory = async () => {
      try {
        // GET /api/v1/{session_id}
        const response = await authFetch(`/api/v1/${sessionId}`)
        if (!response.ok) throw new Error("Failed to fetch history")

        const data = await response.json() as ResponseMessages
        const backendMessages = data.messages ?? []

        if (backendMessages.length > 0) {
          setMessages(
            backendMessages.map((msg: ResponseMessage): Message => ({
              role: msg._role as "user" | "bot1" | "bot2" | "bot3",
              text: msg._content.map(c => c.text ?? "").join("\n\n"),
            }))
          )
        } else {
          // Seed with vulnerability summary when no chat history yet
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

    try {
      // POST /api/v1/{session_id}
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
    <Card className="w-full h-full flex flex-col shadow-sm overflow-hidden pt-6 pb-0">

      {/* Chat area */}
      <div className="flex-1 overflow-y-scroll p-4 text-sm scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
        <div className="flex flex-col gap-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex items-end gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role !== "user" && (
                <div className="w-8 h-8 rounded-full overflow-hidden shrink-0">
                  <img src="/Agent.jpg" className="w-full h-full object-cover" alt="agent" />
                </div>
              )}

              <div
                className={`max-w-[70%] px-3 py-2 rounded-l ${
                  msg.role === "user"
                    ? "bg-blue-800 text-white rounded-br-sm"
                    : "bg-gray-200 text-gray-800 rounded-bl-sm"
                }`}
              >
                {(() => {
                  try {
                    return <VulnerabilityFindingComponent finding={JSON.parse(msg.text) as VulnerabilityFinding} />
                  } catch {
                    return <ReactMarkdown>{msg.text}</ReactMarkdown>
                  }
                })()}
              </div>

              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-full overflow-hidden shrink-0">
                  <img src="/User.png" className="w-full h-full object-cover" alt="user" />
                </div>
              )}
            </div>
          ))}

          {typing && (
            <div className="flex justify-start">
              <div className="bg-gray-200 px-3 py-2 rounded-2xl rounded-bl-sm flex gap-1">
                <span className="animate-bounce">.</span>
                <span className="animate-bounce delay-100">.</span>
                <span className="animate-bounce delay-200">.</span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="border-none p-4 flex flex-col gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What would you like to know?"
          className="resize-none border-none focus-visible:ring-0 p-0 text-lg min-h-40px"
        />

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <UploadSimpleIcon size={22} />
            <Select>
              <SelectTrigger className="border-none shadow-none focus:ring-0 h-auto p-0 gap-1 font-medium">
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
            className="bg-gray-200 hover:bg-gray-300 p-2 rounded-full"
          >
            <SentIcon size={22} color="#6b7280" />
          </button>
        </div>
      </div>
    </Card>
  )
}