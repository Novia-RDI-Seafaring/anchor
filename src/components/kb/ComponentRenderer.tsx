import React from 'react';
import { ListDisplay } from './ListDisplay';
import { TableDisplay } from './TableDisplay';
import { ImageDisplay } from './ImageDisplay';
import { PagePreviewDisplay } from './PagePreviewDisplay';
import { TOCDisplay } from './TOCDisplay';
import { devLog } from '@/lib/logger';

interface UIComponentData {
    component_type: 'list' | 'table' | 'image' | 'page_preview' | 'markdown_table' | 'toc';
    data: any;
    metadata?: any;
}

interface ComponentRendererProps {
    component: UIComponentData;
}

export const ComponentRenderer: React.FC<ComponentRendererProps> = ({ component }) => {
    devLog("ComponentRenderer received:", component.component_type, component.data);
    // ...
    switch (component.component_type) {
        case 'list':
            return <ListDisplay data={component.data} />;

        case 'table':
        case 'markdown_table':
            return <TableDisplay data={component.data} />;

        case 'image':
            return <ImageDisplay data={component.data} />;

        case 'page_preview':
            return <PagePreviewDisplay data={component.data} />;

        case 'toc':
            return <TOCDisplay data={component.data} />;

        default:
            console.warn(`Unknown component type: ${component.component_type}`);
            return null;
    }
};
