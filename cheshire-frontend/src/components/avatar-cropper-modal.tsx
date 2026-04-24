import { useState } from "react"
import Cropper from "react-easy-crop"
import { getCroppedImage, type CroppedAreaPixels } from "@/lib/crop-image"

interface AvatarCropperModalProps {
  imageSrc: string
  onCancel: () => void
  onSave: (file: File, previewUrl: string) => void
}

export default function AvatarCropperModal({
  imageSrc,
  onCancel,
  onSave,
}: AvatarCropperModalProps) {
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [croppedAreaPixels, setCroppedAreaPixels] =
    useState<CroppedAreaPixels | null>(null)

  const handleSave = async () => {
    if (!croppedAreaPixels) return

    const croppedFile = await getCroppedImage(imageSrc, croppedAreaPixels)
    const previewUrl = URL.createObjectURL(croppedFile)

    onSave(croppedFile, previewUrl)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[420px] rounded-xl bg-white p-4 shadow-lg">
        <h2 className="mb-3 text-lg font-semibold">Crop profile photo</h2>

        <div className="relative h-[300px] w-full overflow-hidden rounded-lg bg-gray-900">
          <Cropper
            image={imageSrc}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={(_, croppedPixels) => {
              setCroppedAreaPixels(croppedPixels)
            }}
          />
        </div>

        <div className="mt-4">
          <p className="mb-1 text-sm text-gray-500">Zoom</p>
          <input
            type="range"
            min={1}
            max={3}
            step={0.1}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100"
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={handleSave}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700"
          >
            Save photo
          </button>
        </div>
      </div>
    </div>
  )
}