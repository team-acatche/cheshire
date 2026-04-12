import { useState } from "react"
import { Pencil, Check } from "lucide-react"

type Chat = {
  id: string
  file: { name: string }
}

type Props = {
  profileImage: string
  setProfileImage: (img: string) => void
  userName: string
  setUserName: (name: string) => void
  email: string
  setEmail: (email: string) => void
  chats: Chat[]
}

export default function Account({
  profileImage,
  setProfileImage,
  userName,
  setUserName,
  email,
  setEmail,
  chats
}: Props) {

  const [editing, setEditing] = useState(false)
  const [tempName, setTempName] = useState(userName)
  const [tempEmail, setTempEmail] = useState(email)

  const handleSave = () => {
    setUserName(tempName)
    setEmail(tempEmail)
    setEditing(false)
  }

  return (
    <div className="flex h-full">

      {/* LEFT */}
      <div className="w-[320px] bg-gray-200 flex flex-col items-center justify-center relative">

        <input
          type="file"
          accept="image/*"
          className="hidden"
          id="profile-upload"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (!file) return
            const url = URL.createObjectURL(file)
            setProfileImage(url)
          }}
        />

        <label htmlFor="profile-upload" className="cursor-pointer text-center">
          <img
            src={profileImage}
            className="w-32 h-32 rounded-full object-cover mb-2"
          />
          <p className="text-xs text-gray-500">Change photo</p>
        </label>

        {editing ? (
          <input
            value={tempName}
            onChange={(e) => setTempName(e.target.value)}
            className="text-lg font-semibold text-center bg-transparent border-b border-gray-400 outline-none mt-2"
          />
        ) : (
          <h2 className="text-lg font-semibold mt-2">{userName}</h2>
        )}

        <button
          onClick={() => editing ? handleSave() : setEditing(true)}
          className="absolute bottom-10 w-10 h-10 flex items-center justify-center border rounded-lg hover:bg-gray-300"
        >
          {editing ? <Check size={18} /> : <Pencil size={18} />}
        </button>
      </div>

      {/* RIGHT */}
      <div className="flex-1 p-10">

        <h1 className="text-xl font-semibold mb-2">Information</h1>
        <hr className="mb-6" />

        <p className="font-medium">Email</p>

        {editing ? (
          <input
            value={tempEmail}
            onChange={(e) => setTempEmail(e.target.value)}
            className="border-b border-gray-400 outline-none mb-10"
          />
        ) : (
          <p className="text-gray-600 underline mb-10">
            {email}
          </p>
        )}

        <h1 className="text-xl font-semibold mb-2">Recent Reviews</h1>
        <hr className="mb-6" />

        <div className="space-y-3 text-gray-600">
          {chats.length === 0 ? (
            <p className="text-gray-400">No reviews yet</p>
          ) : (
            chats.slice(0, 5).map((chat) => (
              <div
                key={chat.id}
                className="p-2 border rounded-md text-sm"
              >
                {chat.file.name}
              </div>
            ))
          )}
        </div>

      </div>
    </div>
  )
}