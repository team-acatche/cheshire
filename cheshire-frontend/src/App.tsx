import CheshireSidebar from "./components/cheshire-sidebar";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "./components/ui/sidebar";

export function App() {
    return (
        <>
            <SidebarProvider>
                <CheshireSidebar />
                <SidebarTrigger />
                <SidebarInset>
                    <main>
                        {/* all content goes here */}
                        
                    </main>
                </SidebarInset>
            </SidebarProvider>
        </>
    );
}

export default App;