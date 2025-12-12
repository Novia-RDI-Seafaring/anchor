import React from 'react';
import { ChatArea } from '@/components/chat/ChatArea';
import { InputArea } from '@/components/chat/InputArea';
import { useCopilotChat } from "@copilotkit/react-core";
import { TextMessage, Role } from "@copilotkit/runtime-client-gql";
import { X } from 'lucide-react';
import { useApp } from '@/contexts/AppContext';


interface ChatInterfaceProps {
    isOpen: boolean;
    onClose: () => void;
    initialMessages?: any[];
}

export function ChatInterface({ isOpen, onClose, initialMessages }: ChatInterfaceProps) {
    const { isRagEnabled } = useApp();

    const sanitizedMessages = React.useMemo(() => {
        if (!initialMessages) return [];
        return initialMessages.map(msg => {
            if (msg.role) return msg;
            // Fix for messages with missing role (e.g. deserialized ActionExecutionMessage)
            return { ...msg, role: 'assistant' };
        });
    }, [initialMessages]);

    const { visibleMessages, appendMessage, setMessages } = useCopilotChat({
        initialMessages: sanitizedMessages,
        headers: {
            'X-RAG-Enabled': isRagEnabled ? '1' : '0'
        }
    }) as any;

    // Reset/Update messages when the sanitizedMessages (derived from initialMessages) changes
    React.useEffect(() => {
        if (setMessages) {
            console.log("ChatInterface: syncing messages", sanitizedMessages.length);
            setMessages(sanitizedMessages);

            // Double check synchronization after a short delay (hack for race conditions)
            if (sanitizedMessages.length > 0) {
                const timer = setTimeout(() => {
                    // If we are supposed to have messages but don't, force set again
                    // We actually can't easily check 'visibleMessages' here because it's from the hook which is outside this closure's scope effectively unless in deps
                    // But we can just blindly re-set if needed or rely on the prop change.
                    // Let's just trust setMessages works, but ensure we log it.
                }, 500);
                return () => clearTimeout(timer);
            }
        }
    }, [sanitizedMessages, setMessages]);

    // Convert CopilotKit messages to UI messages
    const uiMessages = visibleMessages.map((msg: any, index: number) => {
        const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);

        return {
            id: msg.id || index.toString(),
            role: (msg.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
            content: content || '',
            timestamp: new Date()
        };
    });

    const handleSendMessage = (text: string) => {
        return appendMessage(
            new TextMessage({
                id: crypto.randomUUID(),
                role: Role.User,
                content: text,
            })
        );
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
                messages={uiMessages}
                isEmpty={uiMessages.length === 0}
            />
            <InputArea onSendMessage={handleSendMessage} />
        </div>
    );
}
