import { useState } from "react"
import { Copy, CopyCheck } from "lucide-react"

interface CodeBlockProps {
  children: string
}

export default function CodeBlock({ children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const text = Array.isArray(children) ? children.join("") : children

    try {
      await navigator.clipboard.writeText(text)
    } catch {
      try {
        const textarea = document.createElement("textarea")
        textarea.value = text
        textarea.style.position = "fixed"
        textarea.style.opacity = "0"
        document.body.appendChild(textarea)
        textarea.focus()
        textarea.select()
        document.execCommand("copy")
        document.body.removeChild(textarea)
      } catch {
        console.error("Copy failed")
        return
      }
    }

    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="relative my-4 group">
      <button
        onClick={handleCopy}
        title={copied ? "Copied!" : "Copy"}
        className="absolute right-3 top-3 rounded-md bg-white/10 backdrop-blur p-1.5 text-white opacity-0 group-hover:opacity-100 hover:bg-white/20 transition"
      >
        {copied ? (
          <CopyCheck size={16} className="text-green-400" />
        ) : (
          <Copy size={16} />
        )}
      </button>

      <pre className="w-full whitespace-pre-wrap break-words rounded-xl bg-zinc-900 p-4 text-sm text-white">
        <code>{children}</code>
      </pre>
    </div>
  )
}