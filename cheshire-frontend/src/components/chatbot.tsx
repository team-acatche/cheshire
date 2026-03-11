import { Card } from "./ui/card"
import { Textarea } from "./ui/textarea"
import UploadSimpleIcon from "./ui/upload-icon"
import { Select, SelectValue, SelectTrigger, SelectContent, SelectItem } from "./ui/select"
import SentIcon from "./ui/sent-icon"

export function Chatbot() {
  return (
    <Card className="w-full p-4 flex flex-col gap-3 rounded-2xl border-gray-200 shadow-sm">
      <Textarea
        placeholder="What would you like to know?"
        className="resize-none border-none focus-visible:ring-0 p-0 text-lg placeholder:text-gray-400"
      />
      
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2">
          <UploadSimpleIcon 
            size={22} 
            className="cursor-pointer text-gray-700 hover:text-black transition-colors"
          />
          
          <Select>
            <SelectTrigger className="border-none shadow-none focus:ring-0 h-auto p-0 gap-1 text-gray-800 font-medium">
              <SelectValue placeholder="Agent 1" />
            </SelectTrigger>
            <SelectContent>
                <SelectItem value="Agent 1">Agent 1</SelectItem>
                <SelectItem value="Agent 2">Agent 2</SelectItem>
                <SelectItem value="Agent 3">Agent 3</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="bg-gray-200 hover:bg-gray-300 p-2 rounded-full cursor-pointer transition-colors">
          <SentIcon 
            size={22} 
            color="#9ca3af"
            className="transform" 
          />
        </div>
      </div>
    </Card>
  )
}