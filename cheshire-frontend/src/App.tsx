import { Button } from "@/components/ui/button";
import { Upload } from "lucide-react";
import CheshireSidebar from "./components/cheshire-sidebar";
import { Card, CardAction, CardContent } from "./components/ui/card";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "./components/ui/sidebar";

export function App() {
    return (
        <>
            <SidebarProvider>
                <CheshireSidebar />
                <SidebarTrigger />
                <SidebarInset>
                    <main>
                        <Card className="w-full max-w-2xl m-50 mx-50">
                            <CardContent/>
                               <CardContent>
                               <p className="text-center font-bold text-xl">Hi! Welcome to Cheshire. Please upload a document to evaluate. Thank you!</p>
                               </CardContent>
                                <CardAction>
                                    <Button type="submit" className="mx-65 w-40">
                                        <Upload />
                                        Upload
                                    </Button>
                                </CardAction>
                        </Card>
                    </main>
                </SidebarInset>
            </SidebarProvider>
        </>
    );
}

export default App;