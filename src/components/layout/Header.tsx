import React from 'react';
import { AgSelect } from '../ui/AgComponents';
import { Cpu, FileText } from 'lucide-react';
import { ModelOption } from '../../types';
import { useApp } from '@/contexts/AppContext';

interface HeaderProps {
  selectedModel: string;
  onModelChange: (id: string) => void;
  models: ModelOption[];
}

export const Header: React.FC<HeaderProps> = ({
  selectedModel,
  onModelChange,
  models
}) => {
  const { documents } = useApp();

  return (
    <header className="h-16 border-b border-neutral-100 dark:border-neutral-800 bg-white/80 dark:bg-neutral-900/80 backdrop-blur-sm flex items-center justify-between px-4 md:px-6 z-30 sticky top-0">

      {/* Left: KB document count */}
      <div className="flex items-center gap-2 text-sm text-neutral-500">
        <FileText size={16} />
        <span>{documents.length} document{documents.length !== 1 ? 's' : ''} in KB</span>
      </div>

      {/* Right: Model Selector */}
      <div className="flex items-center gap-4">
        <AgSelect
          options={models.filter(m => m.type === 'chat' || !m.type)}
          value={selectedModel}
          onChange={onModelChange}
          align="right"
          className="min-w-[240px]"
          icon={<Cpu size={16} />}
        />
      </div>
    </header>
  );
};
