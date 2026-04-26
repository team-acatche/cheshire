import { useState, useEffect } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
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
    // Fetch the stored PDF as an object URL so DocumentPreview can render it
    const docUrl = `/api/v1/${chat.session_id}/document`
    // Use a string URL with authFetch under the hood via DocumentPreview's fetch
    // We pass the URL directly; the browser will use the cached JWT cookie alternative —
    // instead let's fetch it properly and create a blob URL.
    const blob = await authFetch(docUrl)
      .then(r => (r.ok ? r.blob() : null))
      .catch(() => null)

    const objectUrl = blob ? URL.createObjectURL(blob) : null

    const results = await getSessionResults(chat.session_id)
    setFile(objectUrl)
    setFindings(results)
    setCurrentSessionId(chat.session_id)
    setCurrentFileName(chat.title)
    setPage("chat")

    try {
      // Fetch the PDF blob and vulnerability results in parallel
      const docUrl = `/api/v1/${chat.session_id}/document`
      const [blob, results] = await Promise.all([
        authFetch(docUrl).then(r => (r.ok ? r.blob() : null)).catch(() => null),
        getSessionResults(chat.session_id),
      ])

      const objectUrl = blob ? URL.createObjectURL(blob) : null

      // Batch all state updates together — React 18 handles this automatically
      // inside async functions, so no intermediate renders between these lines
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
          <main className={`flex flex-col h-dvh overflow-hidden ${!file ? "items-center justify-center p-9 gap-12" : "p-0 gap-0"}`}>

            {!file && (
              <div className="w-full flex flex-col items-center gap-6">
                <h1 className="text-4xl font-bold tracking-tight text-center">
                    Hi, {user.full_name ?? user.username ?? ""}!
                </h1>
              </div>
            )}

              <Card className={`${!file ? "w-full max-w-md mt-1" : "size-full"} shadow-none`}>
                {isProcessing ? (
                  <CardContent className="col-span-full h-full flex items-center justify-center">
                    <LoadingPage />
                  </CardContent>
                ) : !file ? (
                  <CardContent className="space-y-6 text-center">
                    <div className="space-y-2">
                      <div className="flex flex-col justify-center text-center">
                        <p className="text-muted-foreground text-lg">
                          Welcome to Cheshire. Please upload a PDF document to start the evaluation.
                        </p>
                      </div>
                    </div>

                    <CardAction className="flex justify-center m-auto">
                      <Button asChild className="w-40">
                        <label className="cursor-pointer inline-flex items-center gap-2">
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
                ) : (
                  <ResizablePanelGroup orientation="horizontal" className="h-full">
                    <ResizablePanel defaultSize={65} minSize={30}>
                      <CardContent className="flex flex-col gap-3 size-full overflow-hidden">
                        <DocumentPreview
                          src={file}
                          findings={findings}
                          fileName={currentFileName}
                        />
                      </CardContent>
                    </ResizablePanel>

                    <ResizableHandle withHandle />

                    <ResizablePanel defaultSize={35} minSize={25}>
                      {currentSessionId && (
                        <Chatbot
                          key={currentSessionId}
                          findings={findings}
                          sessionId={currentSessionId}
                          username={user.user_id}
                        />
                      )}
                    </ResizablePanel>
                  </ResizablePanelGroup>
                )}
              </Card>

            {!file && (
              <div className="flex flex-col md:flex-row items-center justify-center gap-16 max-w-7xl mx-auto py-5">
                <div className="flex flex-col md:flex-row items-center gap-8 flex-[1.5]">
                  <div className="flex-shrink-0">
                    <img
                      src="/cheshire.png"
                      alt="Cheshire Logo"
                      className="w-48 h-48 md:w-56 md:h-56 object-contain"
                    />
                  </div>

                  <div className="flex flex-col justify-center text-left max-w-md">
                    <h2 className="text-xl font-bold mb-2 text-slate-800">
                      About Cheshire
                    </h2>
                    <p className="text-base text-muted-foreground leading-relaxed text-justify">
                      Cheshire is an assessment tool designed to identify vulnerabilities
                      in your Technical Document Specification (TDS) using AI analysis.
                      It streamlines the review process by highlighting potential security
                      gaps and ensuring your documentation adheres to industry standards.
                    </p>
                  </div>
                </div>

                <div className="flex-1 border-l border-slate-100 pl-16">
                  <h3 className="text-lg font-semibold uppercase tracking-wider text-slate-400 mb-6">
                    Features
                  </h3>
                  <div className="grid grid-cols-1 gap-6">
                    <div className="flex gap-4">
                      <div className="text-slate-400 font-bold">01</div>
                      <div>
                        <h4 className="font-semibold text-slate-800">Document Preview</h4>
                        <p className="text-base text-muted-foreground">A preview of your uploaded technical document.</p>
                      </div>
                    </div>

                    <div className="flex gap-4">
                      <div className="text-slate-400 font-bold">02</div>
                      <div>
                        <h4 className="font-semibold text-slate-800">Document Highlights</h4>
                        <p className="text-base text-muted-foreground">Automatically find security risks and get clear suggestions on how to fix them.</p>
                      </div>
                    </div>

                    <div className="flex gap-4">
                      <div className="text-slate-400 font-bold">03</div>
                      <div>
                        <h4 className="font-semibold text-slate-800">Chatbot</h4>
                        <p className="text-base text-muted-foreground">Discuss findings directly with the AI.</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </main>
        )}
      </SidebarInset>

    </SidebarProvider>
  )
}
