import { useState } from "react"
import type { Chat } from "@/ChatPage"
import type { AuthUser } from "@/lib/auth"
import { updateStoredUser } from "@/lib/auth"
import AvatarCropperModal from "@/components/avatar-cropper-modal"
import { formatTimestamp, formatChatTimestamp } from "@/lib/helpers/format_timestamps"
import { X } from "lucide-react"
import { toast } from "sonner"

interface AccountProps {
  setProfileImage: (image: string) => void
  user: AuthUser
  chats: Chat[]
  onSelectChat: (chat: Chat) => void
  onClose: () => void
}

export default function Account({ setProfileImage, user, chats, onSelectChat, onClose }: AccountProps) {
  const [avatarSrc, setAvatarSrc] = useState(
    user.avatar_uri && user.avatar_uri !== "avatars/default.png"
      ? `/api/v1/${user.avatar_uri}`
      : "/api/v1/avatars/default.png"
  )

  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [showCropper, setShowCropper] = useState(false)

  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploading, setUploading] = useState(false)

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
        URL.revokeObjectURL(previewUrl)
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
    // Mobile: stacked and scrollable as a whole. Desktop: side-by-side, right column scrolls.
    <div className="relative flex h-full flex-col overflow-y-auto md:flex-row md:overflow-visible">
      <button
        onClick={onClose}
        className="absolute top-3 right-3 z-50 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition hover:bg-muted hover:text-foreground md:top-4 md:right-4"
        aria-label="Close"
      >
        <X size={18} />
      </button>

      {/* Left panel */}
      <div className="relative flex w-full shrink-0 flex-col items-center justify-center gap-3 bg-muted px-4 py-10 md:w-[320px] md:py-0">
        <input
          type="file"
          accept="image/*"
          className="hidden"
          id="profile-upload"
          onChange={(e) => {
            const file = e.target.files?.[0]

            if (!file) return

            if (file.size > 5 * 1024 * 1024) {
              toast.error("File size exceeds 5MB limit.")
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
            className="mx-auto mb-2 h-28 w-28 rounded-full object-cover ring-2 ring-border md:h-32 md:w-32"
          />
          <p className="text-xs text-muted-foreground">
            {uploading ? "Uploading..." : "Change photo"}
          </p>

          {uploading && (
            <div className="mx-auto mt-2 w-32">
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

        <h2 className="max-w-full truncate text-lg font-semibold text-foreground">
          {user.full_name ?? user.username ?? "—"}
        </h2>
      </div>

      {/* Right content */}
      <div className="min-w-0 flex-1 bg-background p-5 md:overflow-y-auto md:p-10">
        <h1 className="text-xl font-semibold mb-2 text-foreground">Information</h1>
        <hr className="mb-6 border-border" />

        <div className="space-y-4 mb-10">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Email</p>
            <p className="break-all text-foreground">{user.email}</p>
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
              <button
                key={chat.session_id}
                type="button"
                onClick={() => onSelectChat(chat)}
                className="flex w-full cursor-pointer flex-col items-start gap-1 rounded-md border border-border bg-card p-3 text-left text-sm text-card-foreground transition-colors hover:bg-muted sm:flex-row sm:items-center sm:justify-between sm:gap-3"
              >
                <span className="min-w-0 max-w-full truncate text-foreground">{chat.title}</span>

                <span
                  className="shrink-0 text-xs text-muted-foreground tabular-nums"
                  title={chat.latestTimestamp ? formatChatTimestamp(chat.latestTimestamp) : ""}
                >
                  Last Activity:{" "}
                  {chat.latestTimestamp
                    ? formatTimestamp(chat.latestTimestamp)
                    : "No activity yet"}
                </span>
              </button>
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