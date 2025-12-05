import React from 'react';
import { AgCard, AgBadge } from '../ui/AgComponents';
import { FileText } from 'lucide-react';

interface BulletItem {
    label: string;
    value: string;
}

interface ListItem {
    title?: string;  // Optional - we don't always show titles
    content?: string;
    items?: BulletItem[];  // For structured bullet points
    score?: number;
    type?: 'bullets' | 'text';
}

interface ListDisplayProps {
    data: {
        items: ListItem[];
    };
}

export const ListDisplay: React.FC<ListDisplayProps> = ({ data }) => {
    if (!data || !data.items || data.items.length === 0) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No results found</p>
            </AgCard>
        );
    }

    // Collect all bullet points from all items
    const allBulletItems: BulletItem[] = [];
    const textItems: Array<{ content: string; score?: number }> = [];

    data.items.forEach((item) => {
        if (item.type === 'bullets' && item.items) {
            allBulletItems.push(...item.items);
        } else if (item.content) {
            textItems.push({ content: item.content, score: item.score });
        }
    });

    // If we have bullet points, show them as a simple list
    if (allBulletItems.length > 0) {
        return (
            <AgCard className="p-6">
                <ul className="space-y-2">
                    {allBulletItems.map((bulletItem, idx) => (
                        <li key={idx} className="text-sm flex gap-2 items-start">
                            <span className="text-brand-600 dark:text-brand-400 mt-1">•</span>
                            <div className="flex-1">
                                <span className="font-medium text-neutral-900 dark:text-white">
                                    {bulletItem.label}:
                                </span>
                                <span className="text-neutral-600 dark:text-neutral-400 ml-2">
                                    {bulletItem.value}
                                </span>
                            </div>
                        </li>
                    ))}
                </ul>
            </AgCard>
        );
    }

    // Fallback: show text items if no bullets found
    if (textItems.length > 0) {
        return (
            <div className="space-y-3">
                {textItems.map((item, idx) => (
                    <AgCard key={idx} className="p-4">
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed">
                            {item.content}
                        </p>
                    </AgCard>
                ))}
            </div>
        );
    }

    return (
        <AgCard className="p-6 text-center">
            <p className="text-neutral-500 dark:text-neutral-400">No content to display</p>
        </AgCard>
    );
};
