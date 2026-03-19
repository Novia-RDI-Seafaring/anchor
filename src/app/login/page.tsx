"use client";

import { signIn } from "next-auth/react";
import { Anchor, Github } from "lucide-react";

export default function LoginPage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-neutral-50 dark:bg-neutral-950">
            <div className="w-full max-w-sm">
                <div className="flex flex-col items-center mb-8">
                    <div className="flex items-center gap-2.5 mb-2">
                        <Anchor className="h-8 w-8 text-neutral-900 dark:text-white" />
                        <span className="text-2xl font-bold text-neutral-900 dark:text-white tracking-tight">ANCHOR</span>
                    </div>
                    <p className="text-sm text-neutral-500 dark:text-neutral-400">Technical knowledge base assistant</p>
                </div>

                <div className="bg-white dark:bg-neutral-900 rounded-2xl border border-neutral-200 dark:border-neutral-800 shadow-sm p-8">
                    <h1 className="text-lg font-semibold text-neutral-900 dark:text-white mb-1">Sign in</h1>
                    <p className="text-sm text-neutral-500 dark:text-neutral-400 mb-6">Choose a provider to continue.</p>

                    <div className="space-y-3">
                        <button
                            onClick={() => signIn("github", { callbackUrl: "/" })}
                            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 text-sm font-medium hover:bg-neutral-700 dark:hover:bg-neutral-100 transition-colors"
                        >
                            <Github size={18} />
                            Continue with GitHub
                        </button>

                        {/* Uncomment when providers are configured:
                        <button
                            onClick={() => signIn("google", { callbackUrl: "/" })}
                            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 text-sm font-medium hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
                        >
                            Continue with Google
                        </button>
                        <button
                            onClick={() => signIn("azure-ad", { callbackUrl: "/" })}
                            className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-lg border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300 text-sm font-medium hover:bg-neutral-50 dark:hover:bg-neutral-800 transition-colors"
                        >
                            Continue with Microsoft
                        </button>
                        */}
                    </div>
                </div>
            </div>
        </div>
    );
}
