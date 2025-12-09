import React, { useState, useEffect } from 'react';
import { AgCard } from '../ui/AgComponents';
import { ChevronLeft, ChevronRight, Loader2, FileText } from 'lucide-react';

interface PagePreviewDisplayProps {
    data: {
        document_id?: string;
        page_numbers?: number[];
        page?: number;  // LLM sometimes sends single page number
        page_number?: number; // Alternative single page number field
        title?: string;
        content?: string;
        content_preview?: string;
        preview?: string;  // LLM sometimes uses this field
        source?: string;
        sections?: any[];  // Can be strings, arrays, or objects
        bboxes?: { bbox: number[]; page_no: number }[]; // Bounding boxes
    };
}

interface PageImage {
    page_number: number;
    image_base64: string;
    width?: number;
    height?: number;
}

const API_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001';

export const PagePreviewDisplay: React.FC<PagePreviewDisplayProps> = ({ data }) => {
    const [images, setImages] = useState<PageImage[]>([]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Normalize page_numbers - accept both page_numbers array and single page number
    const pageNumbers = data?.page_numbers || (data?.page ? [data.page] : []) || (data?.page_number ? [data.page_number] : []);

    // Check if we can fetch page images (need document_id and page_numbers)
    const canFetchImages = data?.document_id && pageNumbers.length > 0;

    useEffect(() => {
        if (!canFetchImages) {
            return;
        }

        const fetchPageImages = async () => {
            try {
                setLoading(true);
                setError(null);

                const response = await fetch(`${API_URL}/api/documents/${data.document_id}/pages/images`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ page_numbers: pageNumbers })
                });

                if (!response.ok) {
                    throw new Error('Failed to fetch page images');
                }

                const result = await response.json();
                if (result.success && result.images && result.images.length > 0) {
                    setImages(result.images);
                } else {
                    setError('No images available for this page');
                }
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load images');
            } finally {
                setLoading(false);
            }
        };

        fetchPageImages();
    }, [data?.document_id, pageNumbers, canFetchImages]);

    const goToPrevious = () => {
        setCurrentIndex((prev) => (prev > 0 ? prev - 1 : prev));
    };

    const goToNext = () => {
        setCurrentIndex((prev) => (prev < images.length - 1 ? prev + 1 : prev));
    };

    // Loading state (only when fetching images)
    if (loading) {
        return (
            <AgCard className="p-8 flex items-center justify-center min-h-[300px]">
                <div className="flex flex-col items-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
                    <span className="text-sm text-neutral-500">Loading page preview...</span>
                </div>
            </AgCard>
        );
    }

    // If we have images, show them
    if (images.length > 0) {
        const currentImage = images[currentIndex];
        if (!currentImage) return null;

        return (
            <AgCard className="overflow-hidden">
                {/* Title if provided */}
                {data.title && (
                    <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700">
                        <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
                            {data.title}
                        </h3>
                    </div>
                )}
                {/* Page image and Bounding Boxes */}
                <div className="relative bg-neutral-100 dark:bg-neutral-900 border-x border-neutral-200 dark:border-neutral-700 flex justify-center p-4 overflow-auto">
                    {/* Wrapper must fit image exactly for overlay to be correct */}
                    <div className="relative inline-block">
                        <img
                            src={`data:image/png;base64,${currentImage.image_base64}`}
                            alt={`Page ${currentImage.page_number}`}
                            className="block max-w-full max-h-[800px] w-auto h-auto"
                        />
                        {/* Bounding Boxes Overlay */}
                        {data.bboxes && data.bboxes.length > 0 && currentImage.width && currentImage.height && (
                            <BoundingBoxOverlay
                                bboxes={data.bboxes.filter(b => b.page_no === currentImage.page_number)}
                                pageWidth={currentImage.width}
                                pageHeight={currentImage.height}
                            />
                        )}
                    </div>
                </div>

                {/* Navigation bar - only show if multiple pages */}
                {images.length > 1 && (
                    <div className="border-t border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 px-4 py-3 flex items-center justify-between">
                        <button
                            onClick={goToPrevious}
                            disabled={currentIndex === 0}
                            className="p-2 rounded-lg hover:bg-neutral-200 dark:hover:bg-neutral-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronLeft size={20} />
                        </button>

                        <span className="text-sm text-neutral-600 dark:text-neutral-400">
                            Page {currentImage.page_number} ({currentIndex + 1} of {images.length})
                        </span>

                        <button
                            onClick={goToNext}
                            disabled={currentIndex === images.length - 1}
                            className="p-2 rounded-lg hover:bg-neutral-200 dark:hover:bg-neutral-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronRight size={20} />
                        </button>
                    </div>
                )}
            </AgCard>
        );
    }


    // Fallback: Show content preview if no images available
    const content = data.content || data.content_preview || data.preview;
    const hasSections = data.sections && data.sections.length > 0;
    const hasContent = data.title || content || pageNumbers.length > 0 || hasSections;

    if (!hasContent) {
        return (
            <AgCard className="p-6 text-center">
                <p className="text-neutral-500 dark:text-neutral-400">No preview data available</p>
            </AgCard>
        );
    }

    return (
        <AgCard className="overflow-hidden">
            {/* Title header */}
            {data.title && (
                <div className="px-4 py-3 bg-neutral-50 dark:bg-neutral-900 border-b border-neutral-200 dark:border-neutral-700 flex items-center gap-2">
                    <FileText size={16} className="text-brand-600 dark:text-brand-400" />
                    <h3 className="text-sm font-semibold text-neutral-700 dark:text-neutral-200">
                        {data.title}
                    </h3>
                </div>
            )}

            {/* Content preview */}
            <div className="p-4 space-y-4">
                {/* Regular content */}
                {content && (
                    <div className="prose prose-sm dark:prose-invert max-w-none">
                        <p className="text-sm text-neutral-600 dark:text-neutral-400 leading-relaxed whitespace-pre-wrap">
                            {content}
                        </p>
                    </div>
                )}

                {/* Sections */}
                {hasSections && (
                    <div className="space-y-3">
                        {data.sections!.map((section: any, idx: number) => {
                            // Handle different section formats
                            let sectionTitle: string | undefined;
                            let sectionContent: string | undefined;

                            if (typeof section === 'string') {
                                // Section is just a string
                                sectionContent = section;
                            } else if (Array.isArray(section)) {
                                // Section is an array like [title, value] or [value1, value2, ...]
                                if (section.length === 2) {
                                    sectionTitle = String(section[0]);
                                    sectionContent = String(section[1]);
                                } else {
                                    sectionContent = section.map(String).join(' | ');
                                }
                            } else if (typeof section === 'object' && section !== null) {
                                // Section is an object - try various field names
                                sectionTitle = section.title || section.heading || section.name || section.engine || section.type;
                                sectionContent = section.content || section.text || section.description || section.value;

                                // If no content found, try to extract key-value pairs
                                if (!sectionContent) {
                                    const entries = Object.entries(section).filter(([key]) =>
                                        !['title', 'heading', 'name'].includes(key)
                                    );
                                    if (entries.length > 0) {
                                        sectionContent = entries.map(([k, v]) => `${k}: ${v}`).join(', ');
                                    }
                                }
                            }

                            // Skip empty sections
                            if (!sectionTitle && !sectionContent) return null;

                            return (
                                <div key={idx} className="border-l-2 border-brand-500 pl-3 py-1">
                                    {sectionTitle && (
                                        <span className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
                                            {sectionTitle}
                                            {sectionContent && ': '}
                                        </span>
                                    )}
                                    {sectionContent && (
                                        <span className="text-sm text-neutral-600 dark:text-neutral-400">
                                            {sectionContent}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* Page info */}
                {pageNumbers.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700">
                        <span className="text-xs text-neutral-500 dark:text-neutral-500">
                            Found on page{pageNumbers.length > 1 ? 's' : ''}: {pageNumbers.join(', ')}
                        </span>
                    </div>
                )}

                {/* Source info */}
                {data.source && (
                    <div className="mt-2">
                        <span className="text-xs text-neutral-400 dark:text-neutral-500">
                            Source: {data.source}
                        </span>
                    </div>
                )}
            </div>
        </AgCard>
    );
};

// BoundingBoxOverlay component
interface BoundingBoxOverlayProps {
    bboxes: { bbox: number[]; page_no: number }[];
    pageWidth: number;
    pageHeight: number;
}

const BoundingBoxOverlay: React.FC<BoundingBoxOverlayProps> = ({ bboxes, pageWidth, pageHeight }) => {
    if (!bboxes || bboxes.length === 0) return null;

    // Detection of coordinate system and scaling:
    // 1. Docling/PyMuPDF bboxes are in PDF Points (72 DPI).
    // 2. Our backend renders images at scale=4.0 (approx 300 DPI).
    // So pageWidth/pageHeight (pixels) are ~4x larger than bbox coordinates.
    // 3. Docling PyMuPDF backend usually implies Bottom-Left origin for PDF coords.

    // We can assume standard A4 is ~595pt width. 
    // If pageWidth is > 2000, we are definitely in high-res pixel space.

    // Calculate scale factor:
    // If we assume the bbox IS in PDF points, we need to normalize it to the image size.
    // But we don't know the PDF point size directly from the frontend prop 'pageWidth' (which is pixels).
    // LUCKILY: The ratio is constant.
    // left % = (x0 / pdfWidth) * 100
    // But we have x0 (pdf points) and pageWidth (pixels).
    // We need pdfWidth.
    // We can estimate pdfWidth if we assume standard 72 vs 300 dpi ratio (scale 4.16?) or just usage scale=4.0 from python code.

    // Better approach: 
    // If x0 is e.g. 50, and pageWidth is 2480.
    // If we just do 50/2480, it's tiny (2%).
    // We need to scale x0 by the same factor the image was scaled.
    // The Python code says `scale = 4.0`.
    // So `x0_pixels = x0_points * 4.0`.

    const SCALE_FACTOR = 4.0; // From backend PageImageService

    return (
        <div className="absolute inset-0 pointer-events-none">
            {bboxes.map((item, idx) => {
                const [x0, y0, x1, y1] = item.bbox;
                if (x0 === undefined || y0 === undefined || x1 === undefined || y1 === undefined) return null;

                // 1. Scale PDF points to Image Pixels
                const scaledX0 = x0 * SCALE_FACTOR;
                const scaledY0 = y0 * SCALE_FACTOR;
                const scaledX1 = x1 * SCALE_FACTOR;
                const scaledY1 = y1 * SCALE_FACTOR;

                // 2. Normalize to Percentage (0-100) relative to image size
                // Coordinate System:
                // Frontend Image: Top-Left (0,0)
                // PDF Source: Bottom-Left (0,0) (Standard PDF)

                // For Bottom-Left origin:
                // y0_pdf is distance from bottom.
                // y1_pdf is distance from bottom (y1 > y0).

                // Top-Left equivalent:
                // top_px = pageHeight - y1_px
                // bottom_px = pageHeight - y0_px

                const left = (scaledX0 / pageWidth) * 100;
                const width = ((scaledX1 - scaledX0) / pageWidth) * 100;

                // Converson for Bottom-Left Origin
                const top = ((pageHeight - scaledY1) / pageHeight) * 100;
                const height = ((scaledY1 - scaledY0) / pageHeight) * 100;

                return (
                    <div
                        key={idx}
                        className="absolute border-2 border-red-500 bg-red-500/20 z-10"
                        style={{
                            left: `${left}%`,
                            top: `${top}%`,
                            width: `${width}%`,
                            height: `${height}%`,
                        }}
                    />
                );
            })}
        </div>
    );
};
