import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

// --- Types ---
interface AgButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'icon';
  size?: 'sm' | 'md' | 'lg' | 'icon';
}

interface AgInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

interface AgSelectProps {
  options: { id: string; label: string; [key: string]: any }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  icon?: React.ReactNode;
  align?: 'left' | 'right';
  className?: string;
}

// --- Components ---

export const AgButton: React.FC<AgButtonProps> = ({ 
  children, 
  variant = 'primary', 
  size = 'md', 
  className = '', 
  ...props 
}) => {
  const baseStyles = "inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:opacity-50 disabled:pointer-events-none";
  
  const variants = {
    primary: "bg-black text-white hover:bg-neutral-800 shadow-sm",
    secondary: "bg-neutral-100 text-neutral-900 hover:bg-neutral-200",
    ghost: "hover:bg-neutral-100 hover:text-neutral-900 text-neutral-600",
    icon: "hover:bg-neutral-100 text-neutral-700 rounded-full",
  };

  const sizes = {
    sm: "h-8 px-3 text-xs",
    md: "h-10 px-4 py-2",
    lg: "h-12 px-8",
    icon: "h-9 w-9",
  };

  return (
    <button 
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`} 
      {...props}
    >
      {children}
    </button>
  );
};

export const AgInput: React.FC<AgInputProps> = ({ label, error, className = '', ...props }) => {
  return (
    <div className="w-full">
      {label && <label className="block text-sm font-medium text-neutral-700 mb-1">{label}</label>}
      <input
        className={`flex h-10 w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm ring-offset-white file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-neutral-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
        {...props}
      />
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
};

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
        className="inline-flex w-full items-center justify-between gap-x-2 rounded-md bg-white px-3 py-2 text-sm font-medium text-neutral-700 shadow-sm hover:bg-neutral-50 border border-transparent hover:border-neutral-200 transition-all"
      >
        <div className="flex items-center gap-2">
          {icon && <span className="text-neutral-500">{icon}</span>}
          <span className="truncate max-w-[200px]">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
        </div>
        <ChevronDown className={`h-4 w-4 text-neutral-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div 
          className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} z-50 mt-2 w-56 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none`}
        >
          <div className="py-1">
            {options.map((option) => (
              <button
                key={option.id}
                onClick={() => {
                  onChange(option.id);
                  setIsOpen(false);
                }}
                className={`group flex w-full items-center justify-between px-4 py-2 text-sm text-left ${
                  option.id === value ? 'bg-neutral-50 text-neutral-900 font-medium' : 'text-neutral-700 hover:bg-neutral-50'
                }`}
              >
                <span>{option.label}</span>
                {option.id === value && <Check className="h-4 w-4 text-brand-600" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export const AgCard: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => {
  return (
    <div className={`rounded-lg border border-neutral-200 bg-white text-neutral-950 shadow-sm ${className}`}>
      {children}
    </div>
  );
};

export const AgBadge: React.FC<{ children: React.ReactNode; variant?: 'default' | 'error' | 'success' }> = ({ children, variant = 'default' }) => {
  const variants = {
    default: "bg-neutral-100 text-neutral-800",
    error: "bg-red-50 text-red-700 border border-red-100",
    success: "bg-green-50 text-green-700 border border-green-100"
  };
  
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  );
};
