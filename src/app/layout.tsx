import type { Metadata } from "next";
import { CopilotKit } from "@copilotkit/react-core";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import { AppProvider } from "@/contexts/AppContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export const metadata: Metadata = {
    title: "Anchor UI",
    description: "Anchor UI Agent",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en">
            <body suppressHydrationWarning>
                <ErrorBoundary>
                    <CopilotKit runtimeUrl="/api/copilotkit" agent="my_agent">
                        <AppProvider>
                            {children}
                        </AppProvider>
                    </CopilotKit>
                </ErrorBoundary>
            </body>
        </html>
    );
}
