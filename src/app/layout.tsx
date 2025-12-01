import type { Metadata } from "next";
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
                    <AppProvider>
                        {children}
                    </AppProvider>
                </ErrorBoundary>
            </body>
        </html>
    );
}
