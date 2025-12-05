import React from 'react';
import { AgCard } from '../ui/AgComponents';

interface TableDisplayProps {
    data: {
        headers: string[];
        rows: string[][];
    };
}

export const TableDisplay: React.FC<TableDisplayProps> = ({ data }) => {
    if (!data?.headers || !data?.rows || data.rows.length === 0) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No table data to display</p>
            </AgCard>
        );
    }

    return (
        <AgCard className="overflow-hidden">
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-neutral-100 dark:bg-neutral-800">
                        <tr>
                            {data.headers.map((header, idx) => (
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
                        {data.rows.map((row, rowIdx) => (
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
