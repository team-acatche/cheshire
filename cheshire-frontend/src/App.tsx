import { useState, useEffect } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import DocumentPreview from "./components/document-preview"
import { NamedFile } from "./types/NamedFile"
import { drawHighlight } from "./lib/helpers/page-highlights"
import { evaluateDocument } from "./lib/helpers/evaluate_document"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import Account from "./components/account"

type Chat = {
  id: string
  file: NamedFile
  findings: VulnerabilityFinding[]
}

export function App() {
  const [file, setFile] = useState<NamedFile | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [chats, setChats] = useState<Chat[]>([])

  const [page, setPage] = useState<"chat" | "account">("chat")

  const [profileImage, setProfileImage] = useState(
    "User.png"
  )

  const [userName, setUserName] = useState("DELA CRUZ, JUAN")
  const [email, setEmail] = useState("delacruz.juan@metrobank.com.ph")

  useEffect(() => {
    const img = localStorage.getItem("profileImage")
    const name = localStorage.getItem("userName")
    const mail = localStorage.getItem("email")

    if (img) setProfileImage(img)
    if (name) setUserName(name)
    if (mail) setEmail(mail)
  }, [])

  useEffect(() => {
    localStorage.setItem("profileImage", profileImage)
    localStorage.setItem("userName", userName)
    localStorage.setItem("email", email)
  }, [profileImage, userName, email])

  const handleNewChat = () => {
    setFile(null)
    setFindings([])
    setPage("chat")
  }

  const handleSelectChat = (chat: Chat) => {
    setFile(chat.file)
    setFindings(chat.findings)
    setPage("chat")
  }

  return (
    <SidebarProvider>

      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        onSelectChat={handleSelectChat}
        onGoAccount={() => setPage("account")}
        profileImage={profileImage}
        userName={userName}
      />

      <SidebarTrigger />

      <SidebarInset>
        {page === "account" ? (
          <Account
            profileImage={profileImage}
            setProfileImage={setProfileImage}
            userName={userName}
            setUserName={setUserName}
            email={email}
            setEmail={setEmail}
            chats={chats} //Connected
          />
        ) : (
          <main className="grid grid-cols-4 place-items-center h-dvh overflow-hidden">

            <Card className={`${!file ? "col-span-full" : "col-span-3 size-full"} mt-2 shadow-none`}>
              {!file ? (
                <CardContent className="size-full space-y-6 text-center">
                  <p className="font-bold text-xl">
                    Hi! Welcome to Cheshire. Please upload a document to evaluate.
                  </p>

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
                            if (file !== null) return;

                            const fileInput = e.target.files?.[0];
                            if (!fileInput) return;

                            if (fileInput.type !== "application/pdf") {
                              alert("Only PDF files are supported.");
                              return;
                            }

                            const _findings = await evaluateDocument(fileInput);
                            const pdfDoc = await drawHighlight(fileInput, _findings);
                            const pdfBytes = await pdfDoc.save();

                            const pdfBlob = new Blob([pdfBytes as BlobPart], {
                              type: "application/pdf",
                            });

                            const newFile = new NamedFile(pdfBlob, fileInput.name)

                            const newChat: Chat = {
                              id: crypto.randomUUID(),
                              file: newFile,
                              findings: _findings,
                            }

                            setChats((prev) => [newChat, ...prev])

                            setFile(newFile)
                            setFindings(_findings)
                          }}
                        />
                      </label>
                    </Button>
                  </CardAction>
                </CardContent>
              ) : (
                <CardContent className="flex flex-col gap-3 size-full">
                  <DocumentPreview src={file} />
                </CardContent>
              )}
            </Card>

            {file && <Chatbot key={file.name} findings={findings} />}

          </main>
        )}
      </SidebarInset>

    </SidebarProvider>
  )
}

export default App