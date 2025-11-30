import { Conversation, ModelOption } from '@/types';

export const MOCK_CONVERSATIONS: Conversation[] = [
    { id: '1', title: 'New Conversation', lastMessageAt: 'Just now', preview: '0 messages · Just now' },
    { id: '2', title: 'React Component Design', lastMessageAt: '2h ago', preview: '4 messages · 2h ago' },
    { id: '3', title: 'Project Anchor Analysis', lastMessageAt: '1d ago', preview: '12 messages · 1d ago' },
];

export const MOCK_MODELS: ModelOption[] = [
    { id: 'llama3.2', label: 'LlamaStack - ollama/llama3.2:3b', provider: 'Ollama' },
    { id: 'gpt-4o', label: 'OpenAI - GPT-4o', provider: 'OpenAI' },
    { id: 'gemini-pro', label: 'Google - Gemini Pro', provider: 'Google' },
];
