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
import { PROVIDER } from "./globals"

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchSessions(): Promise<Chat[]> {
  // GET /api/v1/  — returns sessions for the authenticated user
  return authFetch("/api/v1/")
    .then(r => (r.ok ? r.json() : []))
    .catch(() => [])
}

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

export default function App({ user, onLogout }: AppProps) {
  const [file, setFile]                     = useState<File | string | null>(null)
  const [findings, setFindings]             = useState<VulnerabilityFinding[]>([])
  const [chats, setChats]                   = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing]     = useState(false)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf")
  const [page, setPage]                     = useState<"chat" | "account">("chat")

  // Load sessions on mount
  useEffect(() => {
    fetchSessions().then(sessions =>
      setChats(
        // Backend Session has session_id + title; Chat also needs a findings placeholder
        sessions.map((s: any) => ({
          session_id: s.session_id,
          title: s.title,
          findings: [],
        }))
      )
    )
  }, [])

  const handleNewChat = () => {
    setFile(null)
    setFindings([])
    setCurrentSessionId(null)
    setPage("chat")
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
        profileImage={`/User.png`}
        userName={user.full_name ?? user.username ?? user.email}
      />

      <SidebarTrigger />

      <SidebarInset>
        {page === "account" ? (
          <Account
            user={user}
            chats={chats}
            onLogout={handleLogout}
          />
        ) : (
          <main className="flex flex-col items-center justify-center h-dvh overflow-hidden p-9 gap-12">

            <div className="w-full flex flex-col items-center gap-6">
              <h1 className="text-5xl font-bold tracking-tight text-center">
                  Hi, {user.full_name ?? user.username ?? ""}!
              </h1>

            
              <Card className={`${!file ? "w-full max-w-xl mt-1" : "size-full"} shadow-none`}>
                {isProcessing ? (
                  <CardContent className="col-span-full h-full flex items-center justify-center">
                    <LoadingPage />
                  </CardContent>
                ) : !file ? (
                  <CardContent className="space-y-6 text-center">
                    <div className="space-y-2">
                      <div className="flex flex-col justify-center text-center">
                        <p className="text-muted-foreground text-xl">
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
                    <ResizablePanel defaultSize={75} minSize={30}>
                      <CardContent className="flex flex-col gap-3 size-full overflow-hidden">
                        <DocumentPreview
                          src={file}
                          findings={findings}
                          fileName={currentFileName}
                        />
                      </CardContent>
                    </ResizablePanel>

                    <ResizableHandle withHandle />

                    <ResizablePanel defaultSize={25} minSize={15}>
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
            </div>

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
                  <h2 className="text-2xl font-bold mb-2 text-slate-800">
                    About Cheshire
                  </h2>
                  <p className="text-lg text-muted-foreground leading-relaxed text-justify">
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
          </main>
        )}
      </SidebarInset>
    </SidebarProvider>
  )
}