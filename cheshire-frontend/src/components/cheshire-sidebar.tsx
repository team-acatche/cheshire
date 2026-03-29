import {
    Sidebar,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuItem,
    SidebarContent,
    SidebarFooter
} from "@/components/ui/sidebar";

import {
    CircleUserRound,
    Settings,
    SquarePen,
    MessageSquare
} from "lucide-react";

import AccountDetails from "./account-details";
import { useEffect, useState } from "react";
import { USERNAME } from "@/globals";

type Chat = {
    id: string;
    title: string;
};

type Props = {
    onSelectChat: (chatId: string) => void;
    onNewChat: (chatId: string) => void;
};

export function CheshireSidebar({ onSelectChat, onNewChat }: Props) {
    const [chats, setChats] = useState<Chat[]>([]);
    const [activeChatId, setActiveChatId] = useState<string | null>(null);

    // load chats
    useEffect(() => {
        fetch(`/api/v1/${USERNAME}/chat`)
            .then(res => res.json() as Promise<Chat[]>)
            .then(data => setChats(data))
            .catch(err => console.error("Error loading chats:", err));
    }, []);

    // create new chat
    const createChat = async () => {
        try {
            console.log("Creating chat...");

            const res = await fetch(`/api/v1/${USERNAME}/chat`, {
                method: "POST",
            });

            if (!res.ok) {
                throw new Error("Failed to create chat");
            }

            const chat = await res.json();

            setChats(prev => [chat, ...prev]);
            setActiveChatId(chat.id);

            onNewChat(chat.id);

        } catch (err) {
            console.error("ERROR creating chat:", err);
        }
    };

    return (
        <Sidebar>

            {/* HEADER */}
            <SidebarHeader className="p-5 pt-6 border-b">

                <SidebarMenu className="flex flex-col gap-4">

                    {/* Account */}
                    <SidebarMenuItem className="flex items-center gap-2 m-2">
                        <CircleUserRound size={18} />
                        <AccountDetails />
                    </SidebarMenuItem>

                    {/* ✅ FIXED New Chat */}
                    <SidebarMenuItem>
                        <div
                            className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-muted cursor-pointer"
                            onClick={createChat}
                        >
                            <SquarePen size={18} className="shrink-0" />
                            <span className="leading-none">New Chat</span>
                        </div>
                    </SidebarMenuItem>

                </SidebarMenu>

            </SidebarHeader>

            {/* CONTENT */}
            <SidebarContent className="flex-1 overflow-y-auto">

                <div className="px-3 py-2 text-xs text-muted-foreground uppercase tracking-wide">
                    Your Chats
                </div>

                <SidebarMenu className="flex flex-col gap-1 px-2">

                    {chats.map((chat) => (
                        <SidebarMenuItem key={chat.id}>
                            <div
                                onClick={() => {
                                    setActiveChatId(chat.id);
                                    onSelectChat(chat.id);
                                }}
                                className={`flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer text-sm
                                    ${activeChatId === chat.id
                                        ? "bg-muted font-medium"
                                        : "hover:bg-muted"}
                                `}
                            >
                                <MessageSquare size={16} className="shrink-0" />
                                <span className="truncate leading-none">
                                    {chat.title || "Untitled Chat"}
                                </span>
                            </div>
                        </SidebarMenuItem>
                    ))}

                </SidebarMenu>

            </SidebarContent>

            {/* FOOTER */}
            <SidebarFooter className="flex items-center p-5 border-t gap-2 cursor-pointer">
                <Settings size={18} />
                <span>Settings</span>
            </SidebarFooter>

        </Sidebar>
    );
}

export default CheshireSidebar;