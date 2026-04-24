// src/components/account.tsx
import { useEffect, useState } from "react"
import { Pencil, Check, LogOut } from "lucide-react"
import type { Chat } from "@/ChatPage"
import type { AuthUser } from "@/lib/auth"
import { logout, updateStoredUser } from "@/lib/auth"
import AvatarCropperModal from "@/components/avatar-cropper-modal"

interface AccountProps {
  setProfileImage: (image: string) => void
  user: AuthUser
  chats: Chat[]
  onLogout: () => void
}

export default function Account({ setProfileImage, user, chats, onLogout }: AccountProps) {
  const [editing, setEditing] = useState(false)
  const [displayName, setDisplayName] = useState(user.full_name ?? user.username ?? "")
  const [tempName, setTempName] = useState(user.full_name ?? user.username ?? "")
  const [avatarSrc, setAvatarSrc] = useState(
    user.avatar_uri && user.avatar_uri !== "avatars/default.png"
      ? `/api/v1/${user.avatar_uri}`
      : "/api/v1/avatars/default.png"
  )
  // avatar cropping state
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [showCropper, setShowCropper] = useState(false)
  // uploading state to disable inputs while upload is in progress
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploading, setUploading] = useState(false)
  

  useEffect(() => {
    setDisplayName(user.full_name ?? user.username ?? "")
    setTempName(user.full_name ?? user.username ?? "")
  }, [user])

  const uploadAvatar = async (file: File, previewUrl: string) => {
    setAvatarSrc(previewUrl)
    setProfileImage(previewUrl)
    setUploading(true)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append("avatar", file)

    const xhr = new XMLHttpRequest()

    xhr.open("POST", "/api/v1/avatars", true)

    // If your auth is cookie-based, this is enough:
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

        updateStoredUser({
          avatar_uri: data.avatar_url.replace("/api/v1/", ""),
        })

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

  const handleSave = () => {
    setDisplayName(tempName)
    setEditing(false)

    // TODO: create an endpoint that saves the changes made
  }

  const handleLogout = () => {
    logout()
    onLogout()
  }

  const handleLogout = () => {
    logout()
    onLogout()
  }

  return (
    <div className="flex h-full">
      {/* LEFT panel */}
      <div className="w-[320px] bg-gray-200 flex flex-col items-center justify-center relative gap-3">
        <input
          type="file"
          accept="image/*"
          className="hidden"
          id="profile-upload"
          
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (!file) return

            if (file.size > 5 * 1024 * 1024) { // 5MB limit
              alert("File size exceeds 5MB limit.")
              e.target.value = "" // reset input
              return
            }

            if (file) {
              const reader = new FileReader()

              reader.onload = () => {
                setSelectedImage(reader.result as string)
                setShowCropper(true)
              }
              
              reader.readAsDataURL(file)

              e.target.value = "" // reset input so same file can be selected again if needed
            }
          }}
        />

        <label htmlFor="profile-upload" className={`cursor-pointer text-center ${
          uploading ? "pointer-events-none opacity-50" : ""
          }`}>
          <img
            src={avatarSrc}
            onError={(e) => {
              e.currentTarget.src = "/User.png"
            }}
            alt="Profile"
            className="w-32 h-32 rounded-full object-cover mb-2"
          />
          <p className="text-xs text-gray-500">
            {uploading ? "Uploading..." : "Change photo"}
          </p>

          {uploading && (
            <div className="mt-2 w-32">
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-300">
                <div
                  className="h-full rounded-full bg-gray-700 transition-all"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>

              <p className="mt-1 text-xs text-gray-500">
                Uploading {uploadProgress}%
              </p>
            </div>
          )}
        </label>

        {/* Display name */}
        {editing ? (
          <input
            value={tempName}
            onChange={(e) => setTempName(e.target.value)}
            className="text-lg font-semibold text-center bg-transparent border-b border-gray-400 outline-none"
          />
        ) : (
          <h2 className="text-lg font-semibold">{displayName || "—"}</h2>
        )}

        {/* Edit / Save toggle */}
        <button
          onClick={() => (editing ? handleSave() : setEditing(true))}
          className="absolute bottom-16 w-10 h-10 flex items-center justify-center border rounded-lg hover:bg-gray-300"
          title={editing ? "Save" : "Edit profile"}
        >
          {editing ? <Check size={18} /> : <Pencil size={18} />}
        </button>

        <button
          onClick={handleLogout}
          className="absolute bottom-4 flex items-center gap-1.5 text-sm text-gray-600 hover:text-red-600"
          title="Sign out"
        >
          <LogOut size={15} />
          Sign out
        </button>
      </div>

      {/* RIGHT panel */}
      <div className="flex-1 p-10 overflow-y-auto">
        <h1 className="text-xl font-semibold mb-2">Information</h1>
        <hr className="mb-6" />

        <div className="space-y-4 mb-10">
          <div>
            <p className="text-sm font-medium text-gray-500">Email</p>
            <p className="text-gray-700">{user.email}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">Username</p>
            <p className="text-gray-700">{user.username ?? "—"}</p>
          </div>
        </div>

        <h1 className="text-xl font-semibold mb-2">Recent Reviews</h1>
        <hr className="mb-6" />

        <div className="space-y-3 text-gray-600">
          {chats.length === 0 ? (
            <p className="text-gray-400 text-sm">No reviews yet</p>
          ) : (
            chats.slice(0, 5).map((chat) => (
              <div key={chat.session_id} className="p-2 border rounded-md text-sm">
                {chat.title}
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