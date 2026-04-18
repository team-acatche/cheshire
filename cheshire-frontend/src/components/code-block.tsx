import { useState } from "react"

interface CodeBlockProps {
  children: string
}

export default function CodeBlock({ children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(children)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      console.error("Copy failed")
    }
  }

  return (
    <div className="relative my-4">
      <button
        onClick={handleCopy}
        className="absolute right-3 top-3 text-xs bg-white/10 backdrop-blur px-2 py-1 rounded-md text-white hover:bg-white/20 transition"
      >
        {copied ? "Copied!" : "Copy"}
      </button>

      <pre className="w-full whitespace-pre-wrap break-words rounded-xl bg-zinc-900 p-4 text-sm text-white overflow-x-auto">
        <code>{children}</code>
      </pre>
    </div>
  )
}