import React, { useState, useEffect } from 'react';
import { X, Image, Table, FileText, Zap, Target } from 'lucide-react';

export interface UploadOptions {
    preserveImages: boolean;
    preserveTables: boolean;
    enableOcr: boolean;
    tableMode: 'fast' | 'accurate';
    rememberPreferences: boolean;
}

interface UploadOptionsModalProps {
    isOpen: boolean;
    files: FileList | null;
    onClose: () => void;
    onConfirm: (options: UploadOptions) => void;
}

const defaultOptions: UploadOptions = {
    preserveImages: true,
    preserveTables: true,
    enableOcr: false,
    tableMode: 'fast' as const,
    rememberPreferences: false
};

export function UploadOptionsModal({ isOpen, files, onClose, onConfirm }: UploadOptionsModalProps) {
    const [options, setOptions] = useState<UploadOptions>(defaultOptions);

    // Load saved preferences from localStorage (client-side only)
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const saved = localStorage.getItem('uploadOptions');
            if (saved) {
                try {
                    setOptions(JSON.parse(saved));
                } catch {
                    // Fall back to defaults if parsing fails
                }
            }
        }
    }, []);

    const handleConfirm = () => {
        // Save preferences if requested (client-side only)
        if (typeof window !== 'undefined') {
            if (options.rememberPreferences) {
                localStorage.setItem('uploadOptions', JSON.stringify(options));
            } else {
                localStorage.removeItem('uploadOptions');
            }
        }
        onConfirm(options);
    };

    if (!isOpen) return null;

    const fileNames = files ? Array.from(files).map(f => f.name).join(', ') : '';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white dark:bg-neutral-900 rounded-2xl shadow-2xl w-full max-w-md mx-4 animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
                    <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">Upload Options</h2>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="px-6 py-4 space-y-5">
                    {/* Files */}
                    <div className="flex items-center gap-2 px-3 py-2 bg-neutral-50 dark:bg-neutral-800/50 rounded-lg">
                        <FileText size={16} className="text-neutral-500 dark:text-neutral-400 flex-shrink-0" />
                        <span className="text-sm text-neutral-600 dark:text-neutral-300 truncate">{fileNames}</span>
                    </div>

                    {/* Extract Images */}
                    <label className="flex items-start gap-3 cursor-pointer group">
                        <input
                            type="checkbox"
                            checked={options.preserveImages}
                            onChange={(e) => setOptions({ ...options, preserveImages: e.target.checked })}
                            className="mt-0.5 h-5 w-5 rounded border-neutral-300 dark:border-neutral-700 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                        />
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <Image size={16} className="text-blue-600 dark:text-blue-400" />
                                <span className="font-medium text-neutral-900 dark:text-white">Extract images</span>
                            </div>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                                Preserve diagrams, charts, and illustrations
                            </p>
                        </div>
                    </label>

                    {/* Extract Tables */}
                    <label className="flex items-start gap-3 cursor-pointer group">
                        <input
                            type="checkbox"
                            checked={options.preserveTables}
                            onChange={(e) => setOptions({ ...options, preserveTables: e.target.checked })}
                            className="mt-0.5 h-5 w-5 rounded border-neutral-300 dark:border-neutral-700 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                        />
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <Table size={16} className="text-green-600 dark:text-green-400" />
                                <span className="font-medium text-neutral-900 dark:text-white">Extract tables</span>
                            </div>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                                Preserve table structures and data
                            </p>
                        </div>
                    </label>

                    {/* Enable OCR */}
                    <label className="flex items-start gap-3 cursor-pointer group">
                        <input
                            type="checkbox"
                            checked={options.enableOcr}
                            onChange={(e) => setOptions({ ...options, enableOcr: e.target.checked })}
                            className="mt-0.5 h-5 w-5 rounded border-neutral-300 dark:border-neutral-700 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                        />
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <FileText size={16} className="text-purple-600 dark:text-purple-400" />
                                <span className="font-medium text-neutral-900 dark:text-white">Enable OCR</span>
                            </div>
                            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                                For scanned documents (slower processing)
                            </p>
                        </div>
                    </label>

                    {/* Processing Speed */}
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-neutral-900 dark:text-white">Processing Speed</label>
                        <div className="grid grid-cols-2 gap-3">
                            <label className="flex items-center gap-2 px-3 py-2 border-2 rounded-lg cursor-pointer transition-colors hover:bg-neutral-50 dark:hover:bg-neutral-800/50
                {options.tableMode === 'fast' ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-neutral-200 dark:border-neutral-700'}">
                                <input
                                    type="radio"
                                    name="tableMode"
                                    checked={options.tableMode === 'fast'}
                                    onChange={() => setOptions({ ...options, tableMode: 'fast' })}
                                    className="h-4 w-4 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                                />
                                <Zap size={14} className="text-yellow-600 dark:text-yellow-400" />
                                <span className="text-sm font-medium text-neutral-900 dark:text-white">Fast</span>
                            </label>
                            <label className="flex items-center gap-2 px-3 py-2 border-2 rounded-lg cursor-pointer transition-colors hover:bg-neutral-50 dark:hover:bg-neutral-800/50
                {options.tableMode === 'accurate' ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-neutral-200 dark:border-neutral-700'}">
                                <input
                                    type="radio"
                                    name="tableMode"
                                    checked={options.tableMode === 'accurate'}
                                    onChange={() => setOptions({ ...options, tableMode: 'accurate' })}
                                    className="h-4 w-4 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                                />
                                <Target size={14} className="text-indigo-600 dark:text-indigo-400" />
                                <span className="text-sm font-medium text-neutral-900 dark:text-white">Accurate</span>
                            </label>
                        </div>
                    </div>

                    {/* Remember Preferences */}
                    <label className="flex items-center gap-3 pt-2 border-t border-neutral-200 dark:border-neutral-800 cursor-pointer group">
                        <input
                            type="checkbox"
                            checked={options.rememberPreferences}
                            onChange={(e) => setOptions({ ...options, rememberPreferences: e.target.checked })}
                            className="h-4 w-4 rounded border-neutral-300 dark:border-neutral-700 text-brand-600 focus:ring-brand-500 focus:ring-offset-0"
                        />
                        <span className="text-sm text-neutral-600 dark:text-neutral-400">Remember my preferences</span>
                    </label>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-neutral-200 dark:border-neutral-800">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleConfirm}
                        className="px-4 py-2 text-sm font-medium text-white bg-black dark:bg-white dark:text-black rounded-lg hover:bg-neutral-800 dark:hover:bg-neutral-200 transition-colors"
                    >
                        Upload with Options
                    </button>
                </div>
            </div>
        </div>
    );
}
