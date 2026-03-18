"use client";

import { use } from 'react';
import { HomeApp } from '@/components/HomeApp';

export default function ThreadPage({ params }: { params: Promise<{ threadId: string }> }) {
    const { threadId } = use(params);
    return <HomeApp initialThreadId={threadId} />;
}
