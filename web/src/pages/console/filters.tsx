/**
 * Shared filter controls for the console ledger pages (Interviews, Invitations):
 * a substring-match autocomplete input and a single-select dropdown.
 */

import { useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '../../lib/utils';

export function AutocompleteFilter({
  label,
  value,
  options,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  placeholder: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const query = value.trim().toLowerCase();
  const matches = options.filter(option => option.toLowerCase().includes(query));
  const active = Math.min(highlight, matches.length - 1);

  const selectRow = (index: number) => {
    if (index < 0 || index >= matches.length) return;
    onChange(matches[index]);
    setOpen(false);
    setHighlight(0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (open) setHighlight(h => Math.min(h + 1, matches.length - 1));
      else setOpen(true);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && open && matches.length > 0) {
      e.preventDefault();
      selectRow(active);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <label className="block">
      <span className="label-mono text-on-surface-variant mb-2 block">{label}</span>
      <div className="relative">
        <input
          type="text"
          value={value}
          onChange={e => {
            onChange(e.target.value);
            setOpen(true);
            setHighlight(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="h-10 w-full border border-outline-variant bg-surface-container-lowest px-3 pr-9 text-on-surface text-body-md focus:outline-none focus:border-primary-container placeholder:text-on-surface-variant transition-colors duration-150"
        />
        <ChevronDown
          size={16}
          className={cn(
            'pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant transition-transform duration-150',
            open && 'rotate-180 text-primary-fixed-dim',
          )}
        />
        {open && matches.length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-1 z-40 border border-outline-variant bg-surface shadow-xl max-h-60 overflow-y-auto">
            {matches.map((option, i) => (
              <button
                key={option}
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => selectRow(i)}
                onMouseEnter={() => setHighlight(i)}
                className={cn(
                  'w-full text-left px-3 py-2 text-body-md transition-colors duration-75',
                  i === active ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
                )}
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>
    </label>
  );
}

export function DropdownFilter({
  label,
  value,
  placeholder,
  options,
  onChange,
  clearable = true,
}: {
  label: string;
  value: string;
  placeholder: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  /** false → no "clear back to placeholder" row (for filters with no all-state). */
  clearable?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find(option => option.value === value);

  return (
    <div className="relative">
      <span className="label-mono text-on-surface-variant mb-2 block">{label}</span>
      <button
        type="button"
        onClick={() => setOpen(isOpen => !isOpen)}
        onBlur={() => setOpen(false)}
        className={cn(
          'h-10 w-full border bg-surface-container-lowest px-3 text-left text-body-md transition-colors duration-150',
          'flex items-center justify-between gap-3 focus:outline-none',
          open ? 'border-primary-container text-on-surface' : 'border-outline-variant text-on-surface hover:border-primary-container',
        )}
        aria-expanded={open}
      >
        <span className={current ? 'text-on-surface' : 'text-on-surface-variant'}>
          {current?.label ?? placeholder}
        </span>
        <ChevronDown
          size={16}
          className={cn('text-on-surface-variant transition-transform duration-150', open && 'rotate-180 text-primary-fixed-dim')}
        />
      </button>

      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-40 border border-outline-variant bg-surface shadow-xl max-h-60 overflow-y-auto">
          {clearable && (
            <button
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => {
                onChange('');
                setOpen(false);
              }}
              className={cn(
                'w-full text-left px-3 py-2 text-body-md flex items-center justify-between gap-3 transition-colors duration-75',
                value.length === 0 ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
              )}
            >
              {placeholder}
              {value.length === 0 && <Check size={14} />}
            </button>
          )}
          {options.map(option => {
            const selected = option.value === value;

            return (
              <button
                key={option.value}
                type="button"
                onMouseDown={e => e.preventDefault()}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  'w-full text-left px-3 py-2 text-body-md flex items-center justify-between gap-3 transition-colors duration-75',
                  selected ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface hover:bg-surface-container',
                )}
              >
                {option.label}
                {selected && <Check size={14} />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
