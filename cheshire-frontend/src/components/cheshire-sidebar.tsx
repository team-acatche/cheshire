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
    Settings
} from "lucide-react";
import AccountDetails from "./account-details";


export function CheshireSidebar() {
    return (
        <Sidebar>
            <SidebarHeader className="p-5 pt-6">
                <SidebarMenu>
                    <SidebarMenuItem className="flex items-start gap-1 border-b">
                        <CircleUserRound />
                        <AccountDetails />
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarHeader>
            <SidebarContent>
                
            </SidebarContent>
            <SidebarFooter className="flex flex-row p-5">
                <Settings />
                Setting
            </SidebarFooter>
        </Sidebar>
    );
}

export default CheshireSidebar;