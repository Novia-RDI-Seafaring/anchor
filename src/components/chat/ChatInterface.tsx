import React from 'react';
import { ChatArea } from '@/components/chat/ChatArea';
import { InputArea } from '@/components/chat/InputArea';
import { Message, Role, TextMessage } from "@copilotkit/runtime-client-gql";
import { useCopilotChat } from "@copilotkit/react-core";
import { X } from 'lucide-react';

interface ChatInterfaceProps {
    isOpen: boolean;
    onClose: () => void;
    initialMessages?: any[];
}

export function ChatInterface({ isOpen, onClose, initialMessages }: ChatInterfaceProps) {
    const sanitizedMessages = React.useMemo(() => {
        if (!initialMessages) return [];
        return initialMessages.map(msg => {
            if (msg.role) return msg;
            // Fix for messages with missing role (e.g. deserialized ActionExecutionMessage)
            return { ...msg, role: Role.Assistant };
        });
    }, [initialMessages]);

    const { visibleMessages, appendMessage } = useCopilotChat({
        initialMessages: sanitizedMessages
    });

    // Convert CopilotKit messages to UI messages
    const messages = visibleMessages.map((msg, index) => {
        const isTextMsg = msg.isTextMessage();
        const textMsg = isTextMsg ? (msg as TextMessage) : null;
        const isUser = textMsg?.role === Role.User;
        const content = isTextMsg ? (msg as TextMessage).content : '';

        return {
            id: msg.id || index.toString(),
            role: (isUser ? 'user' : 'assistant') as 'user' | 'assistant',
            content: content,
            timestamp: new Date()
        };
    });

    const handleSendMessage = (text: string) => {
        appendMessage(new TextMessage({ role: Role.User, content: text }));
    };

    if (!isOpen) return null;

    return (
        <div className="w-full md:w-[400px] lg:w-[450px] flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl z-20 absolute md:relative right-0 h-full animate-in slide-in-from-right duration-300">
            {/* Chat Header for Close Button */}
            <div className="h-12 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between px-4 bg-white/50 dark:bg-neutral-900/50 backdrop-blur-sm">
                <span className="text-sm font-medium text-neutral-600 dark:text-neutral-400">Assistant</span>
                <button
                    onClick={onClose}
                    className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    title="Minimize chat"
                >
                    <X size={18} />
                </button>
            </div>

            <ChatArea
                messages={messages}
                isEmpty={messages.length === 0}
            />
            <InputArea onSendMessage={handleSendMessage} />
        </div>
    );
}
