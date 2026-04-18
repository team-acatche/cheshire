import { useState } from "react"
import { Copy, CopyCheck } from "lucide-react"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"

interface CodeBlockProps {
  children: string
  language?: string
}

export default function CodeBlock({ children, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const text = Array.isArray(children) ? children.join("") : children

    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const textarea = document.createElement("textarea")
      textarea.value = text
      textarea.style.position = "fixed"
      textarea.style.opacity = "0"
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
    }

    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="relative my-4 group">
      {/* Copy button */}
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

      {language && (
        <div className="absolute left-3 top-3 text-[10px] px-2 py-0.5 rounded bg-black/30 text-gray-300 uppercase">
          {language}
        </div>
      )}


      <SyntaxHighlighter
        language={language || "text"}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          borderRadius: "0.75rem",
          padding: "2rem 1rem 1rem 1rem",
          fontSize: "0.875rem",
        }}
        wrapLongLines
      >
        {children}
      </SyntaxHighlighter>
    </div>
  )
}