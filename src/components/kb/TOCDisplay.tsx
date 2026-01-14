import React from 'react';
import { List } from 'lucide-react';
import { AgCard } from '../ui/AgComponents';

interface TOCItem {
    text: string;
    level: number;
    page_no?: number;
    type?: string;
}

interface TOCDisplayProps {
    data: {
        toc: TOCItem[];
        filename: string;
        document_id: string;
    };
}

export const TOCDisplay: React.FC<TOCDisplayProps> = ({ data }) => {
    const { toc, filename } = data;

    if (!toc || toc.length === 0) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400 italic">
                    No table of contents available for this document.
                </p>
            </AgCard>
        );
    }

    return (
        <AgCard className="w-full overflow-hidden flex flex-col max-h-[500px]">
            <div className="py-3 px-4 border-b border-neutral-200 dark:border-neutral-800 bg-neutral-50 dark:bg-neutral-900/50 flex items-center gap-2">
                <List className="w-4 h-4 text-brand-600 dark:text-brand-400" />
                <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200 truncate">
                    Table of Contents: {filename}
                </h3>
            </div>
            <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
                <div className="space-y-0.5">
                    {toc.map((item, index) => (
                        <div
                            key={index}
                            className={`
                                px-3 py-1.5 rounded transition-all flex items-center justify-between group
                                hover:bg-neutral-100 dark:hover:bg-neutral-800/50
                                ${item.level === 0 ? 'font-bold text-neutral-900 dark:text-white mt-2 border-l-2 border-brand-500 pl-2' : ''}
                                ${item.level === 1 ? 'font-medium text-neutral-800 dark:text-neutral-100 pl-4' : ''}
                                ${item.level === 2 ? 'text-neutral-600 dark:text-neutral-300 pl-8 text-sm' : ''}
                                ${item.level > 2 ? 'text-neutral-500 dark:text-neutral-400 pl-12 text-xs' : ''}
                            `}
                        >
                            <span className="truncate pr-4">{item.text}</span>
                            {item.page_no !== null && item.page_no !== undefined && (
                                <span className="text-[10px] text-neutral-400 font-mono flex-shrink-0 group-hover:text-brand-600 dark:group-hover:text-brand-400">
                                    p.{item.page_no}
                                </span>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </AgCard>
    );
};
