// src/components/account.tsx
import { useEffect, useState } from "react"
import { Pencil, Check, LogOut } from "lucide-react"
import type { Chat } from "@/ChatPage"
import type { AuthUser } from "@/lib/auth"
import { authFetch, logout, updateStoredUser } from "@/lib/auth"

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

  useEffect(() => {
    setDisplayName(user.full_name ?? user.username ?? "")
    setTempName(user.full_name ?? user.username ?? "")
  }, [user])

  const handleSave = () => {
    setDisplayName(tempName)
    setEditing(false)
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
          onChange={async (e) => {
            const file = e.target.files?.[0]
            if (!file) return

            // Preview immediately
            const reader = new FileReader()
            reader.onloadend = () => {
              setAvatarSrc(reader.result as string)
              setProfileImage(reader.result as string)
            }
            reader.readAsDataURL(file)

            // Upload to backend
            try {
              const formData = new FormData()
              formData.append("avatar", file)

              const res = await authFetch("/api/v1/avatars", {
                method: "POST",
                body: formData,
              })

              if (res.ok) {
                const data = await res.json()
                setAvatarSrc(data.avatar_url)       // updates img in Account
                setProfileImage(data.avatar_url)    // updates img in ChatPage sidebar
                updateStoredUser({ avatar_uri: data.avatar_url.replace("/api/v1/", "") }) // updates stored user for persistence
              }
            } catch (err) {
              console.error("Failed to upload avatar:", err)
            }
          }}
        />

        <label htmlFor="profile-upload" className="cursor-pointer text-center">
          <img
            src={avatarSrc}
            onError={(e) => {
              e.currentTarget.src = "/User.png"
            }}
            alt="Profile"
            className="w-32 h-32 rounded-full object-cover mb-2"
          />
          <p className="text-xs text-gray-500">Change photo</p>
        </label>

        {editing ? (
          <input
            value={tempName}
            onChange={(e) => setTempName(e.target.value)}
            className="text-lg font-semibold text-center bg-transparent border-b border-gray-400 outline-none"
          />
        ) : (
          <h2 className="text-lg font-semibold">{displayName || "—"}</h2>
        )}

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
    </div>
  )
}