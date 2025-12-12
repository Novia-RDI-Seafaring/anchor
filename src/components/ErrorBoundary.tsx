"use client";

import { Component, ReactNode } from 'react';
import { logger } from '@/lib/logger';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        // Log error with full context
        logger.error('React Error Boundary caught an error', error, {
            componentStack: errorInfo.componentStack,
            errorBoundary: true,
        });
    }

    render() {
        if (this.state.hasError) {
            return this.props.fallback || (
                <div className="flex h-screen items-center justify-center bg-white dark:bg-neutral-950">
                    <div className="text-center p-6">
                        <div className="mb-4 text-red-500 text-5xl">!</div>
                        <h2 className="text-xl font-semibold mb-2 text-neutral-900 dark:text-neutral-100">
                            Something went wrong
                        </h2>
                        <p className="text-neutral-600 dark:text-neutral-400 mb-4">
                            {this.state.error?.message || 'An unexpected error occurred'}
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="px-4 py-2 bg-black dark:bg-white text-white dark:text-black rounded-md hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
                        >
                            Reload Page
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
