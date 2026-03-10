export interface Conversation {
    id: string;
    title: string;
    lastMessageAt: string;
    preview: string;
    messages?: any[]; // Using any[] for now to avoid circular dependency with CopilotKit types if not needed here
}

export interface ModelOption {
    id: string;
    label: string;
    provider: string;
    type?: 'chat' | 'embedding';
}
