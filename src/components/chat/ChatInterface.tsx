import React from 'react';
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import { X } from 'lucide-react';
import { InputArea } from '../chat/InputArea';
import { useCopilotChat } from '@copilotkit/react-core';
import { TextMessage } from '@copilotkit/runtime-client-gql';

interface ChatInterfaceProps {
    isOpen: boolean;
    onClose: () => void;
    initialMessages?: any[];
}

// Adapter to make InputArea compatible with CopilotKit's Input component interface
const InputAreaAdapter = (props: any) => {
    // ts-expect-error - appendMessage is deprecated but sendMessage is not yet available in this version
    const { appendMessage } = useCopilotChat();

    const handleSendMessage = (text: string) => {
        // Create a proper TextMessage instance for CopilotKit
        const message = new TextMessage({
            role: 'user' as any, // Type assertion needed due to MessageRole enum
            content: text
        });
        appendMessage(message);
    };

    return (
        <InputArea
            onSendMessage={handleSendMessage}
            disabled={props.inProgress}
        />
    );
};

export function ChatInterface({ isOpen, onClose, initialMessages }: ChatInterfaceProps) {
    if (!isOpen) return null;

    return (
        <div className="w-full md:w-[400px] lg:w-[450px] flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl z-20 absolute md:relative right-0 h-full animate-in slide-in-from-right duration-300">
            {/* Chat Header for Close Button */}
            <div className="h-12 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between px-4 bg-white/50 dark:bg-neutral-900/50 backdrop-blur-sm">
                <span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
                    Assistant
                </span>
                <button
                    onClick={onClose}
                    className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    title="Minimize chat"
                >
                    <X size={18} />
                </button>
            </div>

            {/* CopilotKit's built-in Chat component handles message rendering internally */}
            <div className="flex-1 overflow-hidden">
                <CopilotChat
                    className="h-full"
                    labels={{
                        title: "",
                        initial: "How can I help you today?"
                    }}
                    Input={InputAreaAdapter}
                />
            </div>
        </div>
    );
}
