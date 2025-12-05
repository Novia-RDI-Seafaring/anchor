import React from 'react';
import { AgCard } from '../ui/AgComponents';
import { ExternalLink, FileText } from 'lucide-react';

interface PagePreviewData {
    source: string;
    content: string;
    metadata?: any;
    similarity?: number;
}

interface PagePreviewDisplayProps {
    data: PagePreviewData;
}

export const PagePreviewDisplay: React.FC<PagePreviewDisplayProps> = ({ data }) => {
    if (!data || !data.content) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No preview data available</p>
            </AgCard>
        );
    }

    return (
        <AgCard className="overflow-hidden">
            {/* Header */}
            <div className="border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <FileText size={16} className="text-brand-600 dark:text-brand-400" />
                    <span className="font-medium text-sm text-neutral-900 dark:text-white">
                        {data.source}
                    </span>
                </div>
                <button
                    className="text-neutral-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors"
                    title="Open source"
                >
                    <ExternalLink size={14} />
                </button>
            </div>

            {/* Content */}
            <div className="p-6">
                <div className="prose prose-sm dark:prose-invert max-w-none">
                    <p className="text-neutral-700 dark:text-neutral-300 leading-relaxed whitespace-pre-wrap">
                        {data.content}
                    </p>
                </div>

                {/* Metadata */}
                {data.similarity !== undefined && (
                    <div className="mt-4 pt-4 border-t border-neutral-100 dark:border-neutral-800">
                        <div className="flex items-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
                            <span className="flex items-center gap-1">
                                <span className="font-medium">Relevance:</span>
                                <span className="font-mono">{(data.similarity * 100).toFixed(1)}%</span>
                            </span>
                            {data.metadata && Object.keys(data.metadata).length > 0 && (
                                <span className="flex items-center gap-1">
                                    <span className="font-medium">Metadata:</span>
                                    <span className="font-mono">{Object.keys(data.metadata).length} fields</span>
                                </span>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </AgCard>
    );
};
