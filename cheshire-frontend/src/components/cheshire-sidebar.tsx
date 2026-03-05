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
    SquarePen
} from "lucide-react";
import AccountDetails from "./account-details";

export function CheshireSidebar() {
    return (
        <Sidebar>
            <SidebarHeader className="p-5 pt-6 border-b">
                <SidebarMenu className="flex flex-col gap-4">
                    <SidebarMenuItem className="flex flex-row items-start gap-1 m-2">
                        <CircleUserRound />
                        <AccountDetails />
                    </SidebarMenuItem>
                    <SidebarMenuItem className="flex flex-row gap-2">
                        <SquarePen />
                        New Chat 
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarHeader>
            <SidebarContent>
                
            </SidebarContent>
            <SidebarFooter className="flex flex-row p-5 border-t">
                <Settings />
                Settings 
            </SidebarFooter>
        </Sidebar>
    );
}

export default CheshireSidebar;