import { useState, useEffect } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import DocumentPreview from "./components/document-preview/DocumentPreview"
import {
  evaluateDocument,
  getSessionResults,
} from "./lib/helpers/evaluate_document"
import { authFetch, type AuthUser, clearAuth } from "./lib/auth"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import type { Chat } from "./ChatPage"
import { LoadingPage } from "./components/ui/loadingpage"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import Account from "./components/account"

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchSessions(): Promise<Chat[]> {
  return authFetch("/api/v1/")
    .then(r => (r.ok ? r.json() : []))
    .catch(() => [])
}

async function deleteSession(sessionId: string): Promise<boolean> {
  return authFetch(`/api/v1/${sessionId}`, { method: "DELETE" })
    .then(r => r.ok || r.status === 204)
    .catch(() => false)
}

async function renameSession(sessionId: string, newTitle: string): Promise<boolean> {
  return authFetch(`/api/v1/${sessionId}/rename`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_title: newTitle }),
  })
    .then(r => r.ok)
    .catch(() => false)
}

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

export default function App({ user, onLogout }: AppProps) {
  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf");
  const [page, setPage] = useState<"chat" | "account">("chat")

  // Derive profile image URL from user data, with a fallback to default avatar
  const [profileImage, setProfileImage] = useState(
    user.avatar_uri ? `/api/v1/${user.avatar_uri}` : "/api/v1/avatars/default.png"
  )

  // Load sessions on mount
  useEffect(() => {
    fetchSessions().then(sessions =>
      setChats(
        sessions.map((s: any) => ({
          session_id: s.session_id,
          title: s.title,
          findings: [],
        }))
      )
    )
  }, [])

  const handleNewChat = () => {
    setFindings([])
    setPage("chat")
    setCurrentSessionId(null)
    setFile(null)
  }

  const handleSelectChat = async (chat: Chat) => {
    setIsProcessing(true)
    setPage("chat")

    try {
      const docUrl = `/api/v1/${chat.session_id}/document`

      const [blob, results] = await Promise.all([
        authFetch(docUrl).then(r => (r.ok ? r.blob() : null)).catch(() => null),
        getSessionResults(chat.session_id),
      ])

      const objectUrl = blob ? URL.createObjectURL(blob) : null

      setFile(objectUrl)
      setFindings(results)
      setCurrentSessionId(chat.session_id)
      setCurrentFileName(chat.title)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleDeleteChat = async (sessionId: string) => {
    const ok = await deleteSession(sessionId)
    if (!ok) {
      console.error(`Failed to delete session ${sessionId}`)
      return
    }
    setChats(prev => prev.filter(c => c.session_id !== sessionId))
    if (currentSessionId === sessionId) handleNewChat()
  }

  const handleRenameChat = async (sessionId: string, newTitle: string) => {
    const ok = await renameSession(sessionId, newTitle)
    if (!ok) {
      console.error(`Failed to rename session ${sessionId}`)
      return
    }
    setChats(prev => prev.map(c =>
      c.session_id === sessionId ? { ...c, title: newTitle } : c
    ))
    if (currentSessionId === sessionId) setCurrentFileName(newTitle)
  }

  const handleLogout = () => {
    clearAuth()
    onLogout()
  }

  return (
    <SidebarProvider>

      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        onSelectChat={handleSelectChat}
        onGoAccount={() => setPage("account")}
        profileImage={profileImage || "/User.png"}
        userName={user.full_name ?? user.username ?? user.email}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
      />

      <SidebarTrigger />

      <SidebarInset>
        {page === "account" ? (
          <Account
            setProfileImage={setProfileImage}
            user={user}
            chats={chats}
            onLogout={handleLogout}
          />
        ) : (
          <main className={`h-dvh overflow-hidden ${!file ? "p-8" : "p-0"}`}>
          {isProcessing ? (
            <div className="flex h-full items-center justify-center">
              <Card className="w-full max-w-sm rounded-2xl border border-slate-200 shadow-sm">
                <CardContent className="flex items-center justify-center p-6">
                  <LoadingPage />
                </CardContent>
              </Card>
            </div>
          ) : !file ? (
            <div className="flex h-full flex-col items-center justify-center gap-14">
              <motion.section
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="flex w-full max-w-3xl flex-col items-center text-center"
              >
                <h1 className="text-5xl font-bold tracking-tight text-slate-950">
                  Hi, {user.full_name ?? user.username ?? ""}!
                </h1>

                <Card className="mt-4 w-full max-w-3xl rounded-2xl border border-slate-200 shadow-sm">
                  <CardContent className="space-y-4 p-2 text-center">
                    <p className="text-lg text-muted-foreground text-center">
                      Welcome to Cheshire. Please upload a PDF document to start the evaluation.
                    </p>

                    <CardAction className="w-full flex items-center justify-center">
                      <Button
                        asChild
                        className="w-40 mx-auto block"
                      >
                        <label className="flex items-center justify-center gap-2 cursor-pointer">
                          <Upload className="h-4 w-4" />
                          Upload
                          <input
                            type="file"
                            accept=".pdf"
                            className="hidden"
                            onChange={async (e) => {
                              const fileInput = e.target.files?.[0]
                              if (!fileInput) return

                              if (fileInput.type !== "application/pdf") {
                                alert("Only PDF files are supported.")
                                return
                              }

                              setIsProcessing(true)
                              try {
                                const response = await evaluateDocument(fileInput)
                                if (response === null) {
                                  alert("Failed to evaluate document.")
                                  return
                                }

                                const newChat: Chat = {
                                  session_id: response.session_id,
                                  title: fileInput.name,
                                  findings: response.vulnerabilities,
                                }

                                setChats(prev => [newChat, ...prev])
                                setFile(fileInput)
                                setFindings(response.vulnerabilities)
                                setCurrentSessionId(response.session_id)
                                setCurrentFileName(fileInput.name)
                              } finally {
                                setIsProcessing(false)
                              }
                            }}
                          />
                        </label>
                      </Button>
                    </CardAction>
                  </CardContent>
                </Card>
              </motion.section>

              <motion.section
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, delay: 0.08, ease: "easeOut" }}
                className="flex w-full max-w-6xl flex-col items-center justify-center gap-10 md:flex-row"
              >
                <div className="flex flex-col items-center gap-8 md:flex-row">
                  <img
                    src="/cheshire.png"
                    alt="Cheshire Logo"
                    className="h-44 w-44 object-contain md:h-52 md:w-52"
                  />

                  <div className="max-w-md text-center md:text-left">
                    <h2 className="mb-2 text-xl font-bold text-slate-800">
                      About Cheshire
                    </h2>
                    <p className="text-base leading-relaxed text-muted-foreground md:text-justify">
                      Cheshire is an assessment tool designed to identify vulnerabilities
                      in your Technical Document Specification (TDS) using AI analysis.
                      It streamlines the review process by highlighting potential security
                      gaps and ensuring your documentation adheres to industry standards.
                    </p>
                  </div>
                </div>

                <div className="hidden h-56 w-px bg-slate-100 md:block" />

                <div className="w-full max-w-sm">
                  <h3 className="mb-6 text-lg font-semibold uppercase tracking-wider text-slate-400">
                    Features
                  </h3>

                  <div className="grid gap-6">
                    {[
                      ["01", "Document Preview", "A preview of your uploaded technical document."],
                      ["02", "Document Highlights", "Automatically find security risks and get clear suggestions on how to fix them."],
                      ["03", "Chatbot", "Discuss findings directly with the AI."],
                    ].map(([number, title, description]) => (
                      <div key={number} className="flex gap-4">
                        <div className="font-bold text-slate-400">{number}</div>
                        <div>
                          <h4 className="font-semibold text-slate-800">{title}</h4>
                          <p className="text-base text-muted-foreground">{description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </motion.section>
            </div>
          ) : (
            <Card className="size-full shadow-none">
              <ResizablePanelGroup orientation="horizontal" className="h-full">
                <ResizablePanel defaultSize={60} minSize={30}>
                  <CardContent className="flex size-full flex-col gap-3 overflow-hidden">
                    <DocumentPreview
                      src={file}
                      findings={findings}
                      fileName={currentFileName}
                    />
                  </CardContent>
                </ResizablePanel>

                <ResizableHandle withHandle />

                <ResizablePanel defaultSize={40} minSize={25}>
                  {currentSessionId && (
                    <Chatbot
                      key={currentSessionId}
                      findings={findings}
                      sessionId={currentSessionId}
                      username={user.user_id}
                      profileImage={profileImage}
                    />
                  )}
                </ResizablePanel>
              </ResizablePanelGroup>
            </Card>
          )}
        </main>
        )}
      </SidebarInset>

    </SidebarProvider>
  )
}
