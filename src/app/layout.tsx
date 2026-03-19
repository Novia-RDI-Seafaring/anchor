import type { Metadata } from "next";
import "./globals.css";
import "@copilotkit/react-ui/styles.css";
import { AppProvider } from "@/contexts/AppContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { SessionProvider } from "@/components/providers/SessionProvider";

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
                <SessionProvider>
                    <ErrorBoundary>
                        <AppProvider>
                            {children}
                        </AppProvider>
                    </ErrorBoundary>
                </SessionProvider>
            </body>
        </html>
    );
}
