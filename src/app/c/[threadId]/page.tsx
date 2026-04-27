"use client";

import { use } from 'react';
import { WorkspaceV2App } from '@/components/workspace-v2/WorkspaceV2App';

export default function ThreadPage({ params }: { params: Promise<{ threadId: string }> }) {
    const { threadId } = use(params);
    return <WorkspaceV2App initialThreadId={threadId} />;
}
