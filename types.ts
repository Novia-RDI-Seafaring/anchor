export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

export interface Conversation {
  id: string;
  title: string;
  lastMessageAt: string;
  preview: string;
}

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
}

export interface DatabaseStatus {
  id: string;
  status: 'connected' | 'error' | 'loading';
  label: string;
}
