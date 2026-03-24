import React from 'react';
import { CopilotChat, useChatContext } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";
import type { MessagesProps } from "@copilotkit/react-ui";
import { useCopilotChatInternal } from "@copilotkit/react-core";
import { aguiToGQL } from "@copilotkit/runtime-client-gql";
import { Loader2, X } from 'lucide-react';
import { InputArea } from '../chat/InputArea';

interface ChatInterfaceProps {
    isOpen: boolean;
    onClose: () => void;
}

const InputAreaAdapter = (props: any) => (
    <InputArea
        onSendMessage={(text: string) => props.onSend?.(text)}
        disabled={props.inProgress}
    />
);

function AgentActivityStrip() {
    const { messages = [] } = useCopilotChatInternal();

    let latestLabel = "Thinking";
    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const currentMessage = messages[index];
        if (!currentMessage) continue;
        const legacyMessage: any = aguiToGQL(currentMessage)[0];
        if (!legacyMessage) continue;
        if (legacyMessage?.role === "user") break;
        if (legacyMessage.isActionExecutionMessage?.()) {
            latestLabel = `Calling ${legacyMessage.name || "tool"}`;
            break;
        }
        if (legacyMessage.isAgentStateMessage?.() && legacyMessage.running) {
            latestLabel = legacyMessage.nodeName ? `Thinking · ${legacyMessage.nodeName}` : "Thinking";
            break;
        }
    }

    return (
        <div className="mx-4 my-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-blue-700 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-200">
            <div className="flex items-center gap-2 text-xs font-medium">
                <Loader2 size={14} className="animate-spin" />
                <span>{latestLabel}</span>
            </div>
        </div>
    );
}

function CustomMessages({
    messages,
    inProgress,
    RenderMessage,
    AssistantMessage,
    UserMessage,
    ImageRenderer,
    onRegenerate,
    onCopy,
    onThumbsUp,
    onThumbsDown,
    messageFeedback,
    markdownTagRenderers,
    children,
    chatError,
    ErrorMessage,
}: MessagesProps) {
    const { labels } = useChatContext();
    const { interrupt } = useCopilotChatInternal();
    const messagesContainerRef = React.useRef<HTMLDivElement | null>(null);

    const initialMessages = React.useMemo(() => {
        const initial = labels.initial;
        if (!initial) return [];
        const initialList = Array.isArray(initial) ? initial : [initial];
        return initialList.map((content) => ({
            id: `initial-${content}`,
            role: "assistant" as const,
            content,
        }));
    }, [labels.initial]);

    const displayMessages = [...initialMessages, ...messages];

    React.useEffect(() => {
        const element = messagesContainerRef.current;
        if (!element) return;
        element.scrollTop = element.scrollHeight;
    }, [displayMessages.length, inProgress]);

    return (
        <div ref={messagesContainerRef} className="h-full overflow-y-auto">
            <div className="copilotKitMessagesContainer">
                {displayMessages.map((message, index) => {
                    const legacyMessage: any = aguiToGQL(message as any)[0];
                    if (
                        legacyMessage?.isActionExecutionMessage?.()
                        || legacyMessage?.isAgentStateMessage?.()
                        || legacyMessage?.isResultMessage?.()
                        || legacyMessage?.isImageMessage?.()
                    ) {
                        return null;
                    }

                    return (
                        <RenderMessage
                            key={message.id || index}
                            message={message as any}
                            messages={displayMessages as any}
                            inProgress={inProgress}
                            index={index}
                            isCurrentMessage={index === displayMessages.length - 1}
                            AssistantMessage={AssistantMessage}
                            UserMessage={UserMessage}
                            ImageRenderer={ImageRenderer}
                            onRegenerate={onRegenerate}
                            onCopy={onCopy}
                            onThumbsUp={onThumbsUp}
                            onThumbsDown={onThumbsDown}
                            messageFeedback={messageFeedback}
                            markdownTagRenderers={markdownTagRenderers}
                        />
                    );
                })}
                {displayMessages[displayMessages.length - 1]?.role === "user" && inProgress ? <AgentActivityStrip /> : null}
                {interrupt}
                {chatError && ErrorMessage ? <ErrorMessage error={chatError} isCurrentMessage /> : null}
                {children}
            </div>
        </div>
    );
}

export function ChatInterface({ isOpen, onClose }: ChatInterfaceProps) {
    if (!isOpen) return null;

    return (
        <div className="w-full md:w-[400px] lg:w-[450px] flex flex-col bg-white dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 shadow-xl z-20 absolute md:relative right-0 h-full animate-in slide-in-from-right duration-300">
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

            <div className="flex-1 overflow-hidden">
                <CopilotChat
                    className="h-full"
                    labels={{
                        title: "",
                        initial: "Ask a technical question and I will ground the answer in your loaded documents."
                    }}
                    Input={InputAreaAdapter}
                    Messages={CustomMessages}
                    icons={{ activityIcon: null }}
                />
            </div>
        </div>
    );
}
