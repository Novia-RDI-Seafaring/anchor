import React from 'react';
import { AgCard } from '../ui/AgComponents';

interface TableDisplayProps {
    data: {
        headers?: string[];
        title?: string;  // Alternative to headers (single column header)
        rows: any[];     // Can be string[][] or object[]
    };
}

// Helper to normalize table data from various formats
function normalizeTableData(data: any): { headers: string[]; rows: string[][] } | null {
    if (!data || !data.rows || !Array.isArray(data.rows) || data.rows.length === 0) {
        return null;
    }

    let headers: string[] = [];
    let rows: string[][] = [];

    // Get headers from various sources
    if (data.headers && Array.isArray(data.headers)) {
        headers = data.headers;
    } else if (data.title && typeof data.title === 'string') {
        // If only title is provided, we'll extract headers from the first row object
        headers = []; // Will be set from row keys
    }

    // Process rows - handle both array and object formats
    const firstRow = data.rows[0];

    if (Array.isArray(firstRow)) {
        // Rows are already arrays: [[cell1, cell2], [cell1, cell2]]
        const allRows = data.rows.map((row: any) =>
            Array.isArray(row) ? row.map(String) : [String(row)]
        );

        // If no headers provided, check if the first row looks like headers
        if (headers.length === 0 && allRows[0]) {
            // First row is likely headers if it contains mostly non-numeric text
            const firstRowValues = allRows[0];
            const looksLikeHeaders = firstRowValues.every((val: string) => {
                const trimmed = val.trim();
                // Headers are typically text labels, not pure numbers
                return isNaN(Number(trimmed)) || trimmed.length === 0;
            });

            if (looksLikeHeaders && allRows.length > 1) {
                // Use first row as headers
                headers = firstRowValues;
                rows = allRows.slice(1); // Remove first row from data rows
            } else {
                // First row is data, create generic headers
                headers = firstRowValues.map((_: string, i: number) => `Column ${i + 1}`);
                rows = allRows;
            }
        } else {
            rows = allRows;
        }
    } else if (typeof firstRow === 'object' && firstRow !== null) {
        // Rows are objects: [{key1: val1, key2: val2}, ...]
        // Extract headers from object keys
        headers = Object.keys(firstRow);
        rows = data.rows.map((row: any) =>
            headers.map(key => String(row[key] ?? ''))
        );
    } else if (typeof firstRow === 'string') {
        // Rows might be simple strings - check if they contain key:value patterns
        headers = ['Property', 'Value'];
        rows = data.rows.map((row: string) => {
            if (typeof row === 'string' && row.includes(':')) {
                const parts = row.split(':');
                const key = parts[0] || '';
                const value = parts.slice(1).join(':');
                return [key.trim(), value.trim()];
            }
            return [row, ''];
        });
    }

    // Special case: if title is provided as the table name, use it
    if (data.title && headers.length === 0) {
        headers = ['Property', 'Value'];
    }

    if (headers.length === 0 || rows.length === 0) {
        return null;
    }

    return { headers, rows };
}

export const TableDisplay: React.FC<TableDisplayProps> = ({ data }) => {
    const normalized = normalizeTableData(data);

    if (!normalized) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No table data to display</p>
            </AgCard>
        );
    }

    const { headers, rows } = normalized;

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
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-neutral-100 dark:bg-neutral-800">
                        <tr>
                            {headers.map((header, idx) => (
                                <th
                                    key={idx}
                                    className="px-4 py-3 text-left text-sm font-semibold text-neutral-700 dark:text-neutral-200 border-b border-neutral-200 dark:border-neutral-700"
                                >
                                    {header}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, rowIdx) => (
                            <tr
                                key={rowIdx}
                                className="border-b border-neutral-100 dark:border-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-900/50 transition-colors"
                            >
                                {row.map((cell, cellIdx) => (
                                    <td
                                        key={cellIdx}
                                        className="px-4 py-3 text-sm text-neutral-600 dark:text-neutral-300"
                                    >
                                        {cell}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </AgCard>
    );
};
