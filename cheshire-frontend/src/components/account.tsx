import { useEffect, useState } from "react"
import type { Chat } from "@/ChatPage"
import type { AuthUser } from "@/lib/auth"
import { updateStoredUser, authFetch } from "@/lib/auth"
import AvatarCropperModal from "@/components/avatar-cropper-modal"
import { formatTimestamp } from "@/lib/helpers/format_timestamps"

async function fetchSessionTimestamp(sessionId: string): Promise<string | null> {
  return authFetch(`/api/v1/${sessionId}/latest-timestamp`)
    .then((r) => {
      if (r.status === 204) return null
      if (!r.ok) return null
      return r.json().then((d: { latest_timestamp: string }) => d.latest_timestamp)
    })
    .catch(() => null)
}

interface AccountProps {
  setProfileImage: (image: string) => void
  user: AuthUser
  chats: Chat[]
}

export default function Account({ setProfileImage, user, chats }: AccountProps) {
  const [avatarSrc, setAvatarSrc] = useState(
    user.avatar_uri && user.avatar_uri !== "avatars/default.png"
      ? `/api/v1/${user.avatar_uri}`
      : "/api/v1/avatars/default.png"
  )

  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [showCropper, setShowCropper] = useState(false)

  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploading, setUploading] = useState(false)

  const [chatTimestamps, setChatTimestamps] = useState<
    Record<string, string | null>
  >({})

  useEffect(() => {
    if (chats.length === 0) return

    const loadTimestamps = async () => {
      const entries = await Promise.all(
        chats.slice(0, 5).map(async (chat) => {
          const ts = await fetchSessionTimestamp(chat.session_id)
          return [chat.session_id, ts] as const
        })
      )
      setChatTimestamps(Object.fromEntries(entries))
    }

    loadTimestamps()
  }, [chats])

  const uploadAvatar = async (file: File, previewUrl: string) => {
    setAvatarSrc(previewUrl)
    setProfileImage(previewUrl)
    setUploading(true)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append("avatar", file)

    const xhr = new XMLHttpRequest()
    xhr.open("POST", "/api/v1/avatars", true)
    xhr.withCredentials = true

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100)
        setUploadProgress(percent)
      }
    }

    xhr.onload = () => {
      setUploading(false)

      if (xhr.status >= 200 && xhr.status < 300) {
        const data = JSON.parse(xhr.responseText)

        setAvatarSrc(data.avatar_url)
        setProfileImage(data.avatar_url)
        updateStoredUser({ avatar_uri: data.avatar_url.replace("/api/v1/", "") })
        setUploadProgress(100)
      } else {
        console.error("Upload failed:", xhr.status)
        setUploadProgress(0)
      }
    }

    xhr.onerror = () => {
      console.error("Failed to upload avatar")
      setUploading(false)
      setUploadProgress(0)
    }

    xhr.send(formData)
  }

  return (
    <div className="flex h-full">
      {/* Left panel */}
      <div className="w-[320px] bg-muted flex flex-col items-center justify-center relative gap-3">
        <input
          type="file"
          accept="image/*"
          className="hidden"
          id="profile-upload"
          onChange={(e) => {
            const file = e.target.files?.[0]

            if (!file) return

            if (file.size > 5 * 1024 * 1024) {
              alert("File size exceeds 5MB limit.")
              e.target.value = ""
              return
            }

            const reader = new FileReader()

            reader.onload = () => {
              setSelectedImage(reader.result as string)
              setShowCropper(true)
            }
            
            reader.readAsDataURL(file)

            e.target.value = ""
          }}
        />

        <label
          htmlFor="profile-upload"
          className={`cursor-pointer text-center ${uploading ? "pointer-events-none opacity-50" : ""}`}
        >
          <img
            src={avatarSrc}
            onError={(e) => { e.currentTarget.src = "/User.png" }}
            alt="Profile"
            className="w-32 h-32 rounded-full object-cover mb-2 ring-2 ring-border"
          />
          <p className="text-xs text-muted-foreground">
            {uploading ? "Uploading..." : "Change photo"}
          </p>

          {uploading && (
            <div className="mt-2 w-32">
              <div className="h-2 w-full overflow-hidden rounded-full bg-border">
                <div
                  className="h-full rounded-full bg-foreground transition-all"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Uploading {uploadProgress}%
              </p>
            </div>
          )}
        </label>

        <h2 className="text-lg font-semibold text-foreground">
          {user.full_name ?? user.username ?? "—"}
        </h2>
      </div>

      {/* Right content */}
      <div className="flex-1 p-10 overflow-y-auto bg-background">
        <h1 className="text-xl font-semibold mb-2 text-foreground">Information</h1>
        <hr className="mb-6 border-border" />

        <div className="space-y-4 mb-10">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Email</p>
            <p className="text-foreground">{user.email}</p>
          </div>

          <div>
            <p className="text-sm font-medium text-muted-foreground">Username</p>
            <p className="text-foreground">{user.username ?? "—"}</p>
          </div>
        </div>

        <h1 className="text-xl font-semibold mb-2 text-foreground">Recent Reviews</h1>
        <hr className="mb-6 border-border" />

        <div className="space-y-3">
          {chats.length === 0 ? (
            <p className="text-muted-foreground text-sm">No reviews yet</p>
          ) : (
            chats.slice(0, 5).map((chat) => (
              <div
                key={chat.session_id}
                className="p-3 border border-border rounded-md text-sm flex items-center justify-between bg-card text-card-foreground"
              >
                <span className="text-foreground">{chat.title}</span>

                <span
                  className="text-xs text-muted-foreground tabular-nums hover:text-foreground transition-colors"
                  title={chatTimestamps[chat.session_id] ?? ""}
                >
                  Last Activity:{" "}
                  {chatTimestamps[chat.session_id] !== undefined
                    ? chatTimestamps[chat.session_id]
                      ? formatTimestamp(chatTimestamps[chat.session_id])
                      : "No activity yet"
                    : "Loading..."}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {showCropper && selectedImage && (
        <AvatarCropperModal
          imageSrc={selectedImage}
          onCancel={() => {
            setShowCropper(false)
            setSelectedImage(null)
          }}
          onSave={(file, previewUrl) => {
            setShowCropper(false)
            setSelectedImage(null)
            uploadAvatar(file, previewUrl)
          }}
        />
      )}
    </div>
  )
}