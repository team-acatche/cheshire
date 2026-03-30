import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export function LoadingPage() {
  return (
    <div className="flex flex-col items-center gap-4">
      <Button variant="secondary" disabled size="sm">
        <Spinner data-icon="inline-start" />
        Processing
      </Button>
    </div>
  )
}
