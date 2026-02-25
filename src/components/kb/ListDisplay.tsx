import React from 'react';
import { AgCard } from '../ui/AgComponents';

interface ListDisplayProps {
    data: {
        items: any[];  // Can be various formats
        title?: string;
    };
}

// Normalize list items from various formats the LLM may produce
function normalizeListItems(data: any): string[] {
    if (!data) return [];

    // If data itself is an array, use it directly
    let items = Array.isArray(data) ? data : null;

    // Try the expected key first, then common alternatives
    if (!items) {
        const tryKeys = ['items', 'documents', 'results', 'rows', 'entries', 'list', 'data', 'values'];
        for (const key of tryKeys) {
            if (data[key] && Array.isArray(data[key]) && data[key].length > 0) {
                items = data[key];
                break;
            }
        }
    }

    // Last resort: if data is an object with no recognized array key,
    // collect all its values into items
    if (!items || items.length === 0) {
        // Check if any value in data is an array
        for (const val of Object.values(data)) {
            if (Array.isArray(val) && val.length > 0) {
                items = val as any[];
                break;
            }
        }
    }

    if (!items || !Array.isArray(items) || items.length === 0) {
        return [];
    }

    return items.map((item: any) => {
        // Already a string
        if (typeof item === 'string') {
            return item;
        }

        // Array format - likely [label, value] pair
        if (Array.isArray(item)) {
            if (item.length === 2) {
                // Treat as [label, value] pair
                return `${String(item[0])}: ${String(item[1])}`;
            } else if (item.length === 1) {
                return String(item[0]);
            } else if (item.length > 2) {
                // Join with separator
                return item.map(String).join(' | ');
            }
            return '';
        }

        // Object with various possible text fields
        if (typeof item === 'object' && item !== null) {
            // Document-like objects: show filename with optional metadata
            if (item.filename) {
                const parts = [item.filename];
                if (item.file_size) {
                    const sizeKB = Number(item.file_size) / 1024;
                    const display = sizeKB > 1024
                        ? `${(sizeKB / 1024).toFixed(1)} MB`
                        : `${Math.round(sizeKB)} KB`;
                    parts.push(`(${display})`);
                }
                if (item.source_type) parts.push(`[${item.source_type}]`);
                return parts.join(' ');
            }

            // Try common text field names
            if (item.text) return String(item.text);
            if (item.content) return String(item.content);
            if (item.value) return String(item.value);
            if (item.description) return String(item.description);
            if (item.message) return String(item.message);
            if (item.title) return String(item.title);
            if (item.name) return String(item.name);

            // If it has label and value, format as "label: value"
            if (item.label && item.value) {
                return `${item.label}: ${item.value}`;
            }

            // If it has a property and value (from key-value pairs)
            if (item.property && item.value) {
                return `${item.property}: ${item.value}`;
            }

            // Last resort: format key-value pairs readably instead of raw JSON
            try {
                const keys = Object.keys(item).filter(k => !['id', 'document_id', 'metadata'].includes(k));
                if (keys.length > 0) {
                    return keys.map(k => `${k}: ${item[k]}`).join(' · ');
                }
                return '';
            } catch {
                return '';
            }
        }

        // Fallback for other types
        return String(item);
    }).filter((item: string) => item.trim() !== '');
}

export const ListDisplay: React.FC<ListDisplayProps> = ({ data }) => {
    const items = normalizeListItems(data);

    if (items.length === 0) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No results found</p>
            </AgCard>
        );
    }

    return (
        <AgCard className="overflow-hidden">
            {/* Show title if provided */}
            {data.title && (
                <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700">
                    <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
                        {data.title}
                    </h3>
                </div>
            )}
            <div className="p-4">
                <ul className="space-y-2">
                    {items.map((item, idx) => {
                        // Check if item contains a colon (key-value format)
                        const hasColon = item.includes(':') && item.indexOf(':') < 50;

                        if (hasColon) {
                            const colonIndex = item.indexOf(':');
                            const label = item.substring(0, colonIndex).trim();
                            const value = item.substring(colonIndex + 1).trim();

                            return (
                                <li key={idx} className="text-sm flex gap-2 items-start">
                                    <span className="text-brand-600 dark:text-brand-400 mt-0.5 flex-shrink-0">-</span>
                                    <div className="flex-1 min-w-0">
                                        <span className="font-medium text-neutral-900 dark:text-white">
                                            {label}:
                                        </span>
                                        <span className="text-neutral-600 dark:text-neutral-400 ml-1">
                                            {value}
                                        </span>
                                    </div>
                                </li>
                            );
                        }

                        return (
                            <li key={idx} className="text-sm flex gap-2 items-start">
                                <span className="text-brand-600 dark:text-brand-400 mt-0.5 flex-shrink-0">-</span>
                                <span className="text-neutral-700 dark:text-neutral-300 flex-1">
                                    {item}
                                </span>
                            </li>
                        );
                    })}
                </ul>
            </div>
        </AgCard>
    );
};
