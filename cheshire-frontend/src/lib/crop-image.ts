export interface CroppedAreaPixels {
  x: number
  y: number
  width: number
  height: number
}

export async function getCroppedImage(
  imageSrc: string,
  crop: CroppedAreaPixels,
  fileName = "avatar.png"
): Promise<File> {
  const image = await createImage(imageSrc)

  const canvas = document.createElement("canvas")
  const ctx = canvas.getContext("2d")

  if (!ctx) {
    throw new Error("Could not create canvas context")
  }

  canvas.width = crop.width
  canvas.height = crop.height

  ctx.drawImage(
    image,
    crop.x,
    crop.y,
    crop.width,
    crop.height,
    0,
    0,
    crop.width,
    crop.height
  )

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("Failed to crop image"))
        return
      }

      resolve(new File([blob], fileName, { type: "image/png" }))
    }, "image/png")
  })
}

function createImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.addEventListener("load", () => resolve(image))
    image.addEventListener("error", reject)
    image.src = url
  })
}