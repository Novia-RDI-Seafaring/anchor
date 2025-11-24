import React from 'react';
import { AgSelect, AgBadge } from '../ui/AgComponents';
import { Database, Cpu } from 'lucide-react';
import { DatabaseStatus, ModelOption } from '../../types';

interface HeaderProps {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  selectedModel: string;
  onModelChange: (id: string) => void;
  dbStatus: DatabaseStatus;
  models: ModelOption[];
}

export const Header: React.FC<HeaderProps> = ({ 
  selectedModel, 
  onModelChange, 
  dbStatus,
  models
}) => {
  const dbOptions = [
    { id: 'default', label: dbStatus.label }
  ];

  return (
    <header className="h-16 border-b border-neutral-100 bg-white/80 backdrop-blur-sm flex items-center justify-between px-4 md:px-6 z-10 sticky top-0">
      
      {/* Left: Database Status Indicator */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Database size={16} className={dbStatus.status === 'error' ? 'text-red-500' : 'text-neutral-500'} />
          <AgSelect 
            options={dbOptions}
            value="default"
            onChange={() => {}}
            className="w-48"
          />
          {dbStatus.status === 'error' && (
             <span className="hidden md:inline-block h-2 w-2 rounded-full bg-red-500 animate-pulse"></span>
          )}
        </div>
      </div>

      {/* Right: Model Selector */}
      <div className="flex items-center gap-4">
        <div className="hidden md:flex items-center text-xs text-neutral-400 gap-1 mr-2">
           <span>RAG Pipeline</span>
           <span className="w-px h-3 bg-neutral-300 mx-1"></span>
           <span className="text-green-600 font-medium">Ready</span>
        </div>
        <AgSelect 
          options={models}
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
