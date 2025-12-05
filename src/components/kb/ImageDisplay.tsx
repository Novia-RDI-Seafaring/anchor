import React from 'react';
import { AgCard } from '../ui/AgComponents';
import { Image as ImageIcon } from 'lucide-react';

interface ImageItem {
    url: string;
    caption?: string;
    source?: string;
    similarity?: number;
}

interface ImageDisplayProps {
    data: {
        images: ImageItem[];
        message?: string;
    };
}

export const ImageDisplay: React.FC<ImageDisplayProps> = ({ data }) => {
    if (!data?.images || data.images.length === 0) {
        return (
            <AgCard className="p-6 text-center">
                <div className="flex flex-col items-center gap-2 text-neutral-400 dark:text-neutral-500">
                    <ImageIcon size={32} />
                    <p>{data?.message || 'No images found in results'}</p>
                </div>
            </AgCard>
        );
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.images.map((image, idx) => (
                <AgCard key={idx} className="overflow-hidden group">
                    <div className="aspect-video bg-neutral-100 dark:bg-neutral-800 relative overflow-hidden">
                        <img
                            src={image.url}
                            alt={image.caption || `Image ${idx + 1}`}
                            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                            loading="lazy"
                            onError={(e) => {
                                // Fallback for broken images
                                const target = e.target as HTMLImageElement;
                                target.style.display = 'none';
                                target.parentElement?.classList.add('flex', 'items-center', 'justify-center');
                                const fallback = document.createElement('div');
                                fallback.className = 'text-neutral-400 dark:text-neutral-500 text-center p-4';
                                fallback.innerHTML = `<svg class="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg><p class="text-sm">Image unavailable</p>`;
                                target.parentElement?.appendChild(fallback);
                            }}
                        />
                    </div>

                    {(image.caption || image.source) && (
                        <div className="p-3 border-t border-neutral-100 dark:border-neutral-800">
                            {image.caption && (
                                <p className="text-sm font-medium text-neutral-900 dark:text-white mb-1">
                                    {image.caption}
                                </p>
                            )}
                            <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
                                {image.source && <span className="truncate">{image.source}</span>}
                                {image.similarity !== undefined && (
                                    <span className="ml-2 font-mono flex-shrink-0">
                                        {(image.similarity * 100).toFixed(0)}%
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </AgCard>
            ))}
        </div>
    );
};
