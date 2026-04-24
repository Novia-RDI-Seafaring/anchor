import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

interface AgSelectProps {
  options: { id: string; label: string;[key: string]: any }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  icon?: React.ReactNode;
  align?: 'left' | 'right';
  className?: string;
}

export const AgSelect: React.FC<AgSelectProps> = ({
  options,
  value,
  onChange,
  placeholder = "Select...",
  icon,
  align = 'left',
  className = ''
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find(o => o.id === value);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className={`relative inline-block text-left ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex w-full items-center justify-between gap-x-2 rounded-md bg-white dark:bg-neutral-900 px-3 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-200 shadow-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 border border-transparent dark:border-neutral-800 hover:border-neutral-200 dark:hover:border-neutral-700 transition-all"
      >
        <div className="flex items-center gap-2">
          {icon && <span className="text-neutral-500 dark:text-neutral-400">{icon}</span>}
          <span className="truncate max-w-[200px]">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
        </div>
        <ChevronDown className={`h-4 w-4 text-neutral-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div
          className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} z-50 mt-2 w-56 origin-top-right rounded-md bg-white dark:bg-neutral-900 shadow-lg ring-1 ring-black ring-opacity-5 dark:ring-neutral-800 focus:outline-none`}
        >
          <div className="py-1">
            {options.map((option) => (
              <button
                key={option.id}
                onClick={() => {
                  onChange(option.id);
                  setIsOpen(false);
                }}
                className={`group flex w-full items-center justify-between px-4 py-2 text-sm text-left ${option.id === value
                  ? 'bg-neutral-50 dark:bg-neutral-800 text-neutral-900 dark:text-white font-medium'
                  : 'text-neutral-700 dark:text-neutral-300 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                  }`}
              >
                <span>{option.label}</span>
                {option.id === value && <Check className="h-4 w-4 text-brand-600 dark:text-brand-400" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
