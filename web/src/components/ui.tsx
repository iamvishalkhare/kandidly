/**
 * Kandidly Design System — minimal dark component kit
 * All components bake the dark palette directly. No theme switching.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import { X, Check, Copy, AlertCircle, Info, CheckCircle2, XCircle } from 'lucide-react';
import { cn } from '../lib/utils';

// ─── Button ──────────────────────────────────────────────────────────────────

type ButtonVariant = 'primary' | 'ghost' | 'danger' | 'outline';
type ButtonSize    = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leftIcon?: React.ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  leftIcon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const base =
    'inline-flex items-center justify-center gap-2 font-mono font-medium uppercase tracking-[0.1em] transition-colors duration-150 focus-visible:outline-none focus-visible:border-[var(--accent)] disabled:opacity-40 disabled:pointer-events-none select-none';

  const variants: Record<ButtonVariant, string> = {
    primary:
      'bg-[var(--accent)] text-[var(--on-primary-container)] border border-[var(--accent)] hover:bg-transparent hover:text-[var(--primary)]',
    ghost:
      'border border-transparent bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]',
    outline:
      'border border-[var(--border)] bg-transparent text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--primary)]',
    danger:
      'border border-[var(--error-container)] bg-transparent text-[var(--error)] hover:bg-[var(--error-container)] hover:text-[var(--on-error-container)]',
  };

  const sizes: Record<ButtonSize, string> = {
    sm: 'h-7 px-3 text-2xs',
    md: 'h-9 px-4 text-xs',
    lg: 'h-10 px-5 text-xs',
  };

  return (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg
          className="animate-spin size-4"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        leftIcon
      )}
      {children}
    </button>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export function Card({ children, className, padding = 'md', ...props }: CardProps) {
  const paddings = { none: '', sm: 'p-4', md: 'p-5', lg: 'p-6' };
  return (
    <div
      className={cn(
        'rounded-lg border border-[var(--border)] bg-[var(--surface)]',
        paddings[padding],
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

// ─── Badge / Chip ─────────────────────────────────────────────────────────────

type BadgeColor = 'emerald' | 'amber' | 'red' | 'blue' | 'violet' | 'zinc';

interface BadgeProps {
  color?: BadgeColor;
  children: React.ReactNode;
  className?: string;
}

const badgeStyles: Record<BadgeColor, string> = {
  emerald: 'bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)] border-[var(--emerald-chip-text)]',
  amber:   'bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)] border-[var(--amber-chip-text)]',
  red:     'bg-[var(--red-chip-bg)] text-[var(--red-chip-text)] border-[var(--red-chip-text)]',
  blue:    'bg-[var(--blue-chip-bg)] text-[var(--blue-chip-text)] border-[var(--accent)]',
  violet:  'bg-[var(--violet-chip-bg)] text-[var(--violet-chip-text)] border-[var(--violet-chip-text)]',
  zinc:    'bg-transparent text-[var(--text-secondary)] border-[var(--border)]',
};

export function Badge({ color = 'zinc', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 font-mono text-2xs font-medium uppercase tracking-[0.1em] border',
        badgeStyles[color],
        className
      )}
    >
      {children}
    </span>
  );
}

// StateBadge: maps application/requisition/interview states to colors
const stateColors: Record<string, BadgeColor> = {
  // Application states
  registered:      'zinc',
  form_in_progress:'blue',
  form_submitted:  'blue',
  plan_ready:      'violet',
  in_lobby:        'violet',
  in_interview:    'amber',
  completed:       'emerald',
  scored:          'emerald',
  reviewed:        'emerald',
  // Requisition states
  draft:   'zinc',
  open:    'emerald',
  paused:  'amber',
  closed:  'red',
  // Template/rubric states
  published: 'emerald',
  // Generic
  pending:   'amber',
  failed:    'red',
  processing:'blue',
};

const stateLabels: Record<string, string> = {
  form_in_progress: 'In Progress',
  form_submitted:   'Submitted',
  plan_ready:       'Plan Ready',
  in_lobby:         'In Lobby',
  in_interview:     'Interviewing',
};

export function StateBadge({ state }: { state: string }) {
  const color = stateColors[state] ?? 'zinc';
  const label = stateLabels[state] ?? state.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  return <Badge color={color}>{label}</Badge>;
}

// ─── Input ────────────────────────────────────────────────────────────────────

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export function Input({ label, error, hint, className, id: idProp, ...props }: InputProps) {
  const uid = useId();
  const id = idProp ?? uid;

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={id} className="label-mono block text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <input
        id={id}
        className={cn(
          'w-full border bg-[var(--background)] px-3 py-2 text-sm text-[var(--text-primary)]',
          'placeholder:text-[var(--text-muted)]',
          'focus:outline-none focus:ring-0 focus:border-[var(--accent)]',
          'transition-colors duration-150',
          error ? 'border-[var(--error)]' : 'border-[var(--border)]',
          className
        )}
        {...props}
      />
      {error && <p className="font-mono text-2xs text-[var(--error)]">{error}</p>}
      {hint && !error && <p className="text-xs text-[var(--text-muted)]">{hint}</p>}
    </div>
  );
}

// ─── Textarea ─────────────────────────────────────────────────────────────────

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  charCount?: number;
}

export function Textarea({ label, error, charCount, className, id: idProp, ...props }: TextareaProps) {
  const uid = useId();
  const id = idProp ?? uid;

  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex justify-between items-baseline">
          <label htmlFor={id} className="label-mono block text-[var(--text-secondary)]">
            {label}
          </label>
          {charCount !== undefined && (
            <span className="font-mono text-2xs text-[var(--text-muted)] tabular-nums">{charCount}</span>
          )}
        </div>
      )}
      <textarea
        id={id}
        className={cn(
          'w-full border bg-[var(--background)] px-3 py-2 text-sm text-[var(--text-primary)]',
          'placeholder:text-[var(--text-muted)] resize-none',
          'focus:outline-none focus:ring-0 focus:border-[var(--accent)]',
          'transition-colors duration-150 min-h-24',
          error ? 'border-[var(--error)]' : 'border-[var(--border)]',
          className
        )}
        {...props}
      />
      {error && <p className="font-mono text-2xs text-[var(--error)]">{error}</p>}
    </div>
  );
}

// ─── Select ──────────────────────────────────────────────────────────────────

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
  placeholder?: string;
}

export function Select({ label, error, options, placeholder, className, id: idProp, ...props }: SelectProps) {
  const uid = useId();
  const id = idProp ?? uid;

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={id} className="label-mono block text-[var(--text-secondary)]">
          {label}
        </label>
      )}
      <select
        id={id}
        className={cn(
          'w-full border bg-[var(--background)] px-3 py-2 text-sm text-[var(--text-primary)]',
          'focus:outline-none focus:ring-0 focus:border-[var(--accent)]',
          'transition-colors duration-150 appearance-none',
          error ? 'border-[var(--error)]' : 'border-[var(--border)]',
          className
        )}
        {...props}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <p className="font-mono text-2xs text-[var(--error)]">{error}</p>}
    </div>
  );
}

// ─── Table primitives ─────────────────────────────────────────────────────────

export function Table({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('w-full overflow-x-auto', className)}>
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Thead({ children }: { children: React.ReactNode }) {
  return (
    <thead>
      <tr className="border-b border-[var(--border)]">{children}</tr>
    </thead>
  );
}

export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        'px-4 py-3 text-left font-mono text-2xs font-medium text-[var(--text-muted)] uppercase tracking-[0.15em]',
        className
      )}
    >
      {children}
    </th>
  );
}

export function Tbody({ children }: { children: React.ReactNode }) {
  return <tbody className="divide-y divide-[var(--border)]">{children}</tbody>;
}

export function Tr({
  children,
  onClick,
  className,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <tr
      className={cn(
        'transition-colors duration-150',
        onClick ? 'cursor-pointer hover:bg-[var(--surface-hover)]' : '',
        className
      )}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

export function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <td className={cn('px-4 py-3 text-[var(--text-primary)]', className)}>{children}</td>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('skeleton', className)} {...props} />;
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn('h-4', i === lines - 1 && lines > 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  );
}

// ─── EmptyState ───────────────────────────────────────────────────────────────

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center gap-3">
      {icon && (
        <div className="size-12 rounded-xl bg-[var(--surface-hover)] flex items-center justify-center text-[var(--text-muted)] mb-1">
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      {description && <p className="text-xs text-[var(--text-muted)] max-w-xs">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

// ─── Modal ────────────────────────────────────────────────────────────────────

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

export function Modal({ open, onClose, title, children, size = 'md' }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      {/* Panel */}
      <div
        className={cn(
          'relative w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-xl',
          widths[size]
        )}
        onClick={e => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────

type ToastType = 'info' | 'success' | 'error' | 'warning';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastCtx = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const add = useCallback((message: string, type: ToastType = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3500);
  }, []);

  const icons: Record<ToastType, React.ReactNode> = {
    info:    <Info size={14} />,
    success: <CheckCircle2 size={14} />,
    error:   <XCircle size={14} />,
    warning: <AlertCircle size={14} />,
  };

  const colors: Record<ToastType, string> = {
    info:    'border-[var(--accent)] text-[var(--blue-chip-text)]',
    success: 'border-[var(--emerald-chip-text)] text-[var(--emerald-chip-text)]',
    error:   'border-[var(--error)] text-[var(--error)]',
    warning: 'border-[var(--amber-chip-text)] text-[var(--amber-chip-text)]',
  };

  return (
    <ToastCtx.Provider value={{ toast: add }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-xs w-full pointer-events-none">
        {toasts.map(t => (
          <div
            key={t.id}
            className={cn(
              'flex items-center gap-2 rounded-lg border bg-[var(--surface)] px-4 py-3 text-sm shadow-xl pointer-events-auto',
              colors[t.type]
            )}
          >
            {icons[t.type]}
            <span className="text-[var(--text-primary)]">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

// oxlint-disable-next-line react/only-export-components
export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error('useToast must be used inside ToastProvider');
  return ctx;
}

// ─── CopyButton ───────────────────────────────────────────────────────────────

export function CopyButton({ value, className }: { value: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      onClick={copy}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-all duration-150',
        className
      )}
    >
      {copied ? (
        <>
          <Check size={12} className="text-[var(--emerald-chip-text)]" />
          Copied
        </>
      ) : (
        <>
          <Copy size={12} />
          Copy
        </>
      )}
    </button>
  );
}

// ─── StatChip ─────────────────────────────────────────────────────────────────

export function StatChip({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border border-[var(--border)] bg-[var(--surface)] p-4 space-y-1">
      <p className="label-mono text-[var(--text-muted)]">{label}</p>
      <p className="font-display text-3xl font-bold tracking-tight tabular text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

// ─── PageHeader ───────────────────────────────────────────────────────────────

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  back?: React.ReactNode;
}

export function PageHeader({ title, description, actions, back }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        {back && <div className="mb-2">{back}</div>}
        <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--text-primary)]">{title}</h1>
        {description && <p className="mt-1 text-sm text-[var(--text-muted)]">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

// ─── Divider ─────────────────────────────────────────────────────────────────

export function Divider({ className }: { className?: string }) {
  return <hr className={cn('border-[var(--border)]', className)} />;
}

// ─── Spinner ─────────────────────────────────────────────────────────────────

export function Spinner({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={cn('animate-spin text-[var(--text-muted)]', className)}
      width={size}
      height={size}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

// ─── ErrorState ───────────────────────────────────────────────────────────────

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center gap-3">
      <div className="size-12 border border-[var(--error)] bg-[var(--red-chip-bg)] flex items-center justify-center">
        <AlertCircle size={20} className="text-[var(--error)]" />
      </div>
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      {message && <p className="text-xs text-[var(--text-muted)] max-w-xs">{message}</p>}
      {onRetry && (
        <Button variant="ghost" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

interface TabsProps {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="flex gap-1 border-b border-[var(--border)] mb-5">
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            'px-4 py-2.5 font-mono text-xs font-medium uppercase tracking-[0.1em] border-b-2 -mb-px transition-colors duration-150',
            active === tab.id
              ? 'border-[var(--accent)] text-[var(--primary)]'
              : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ─── Stepper ─────────────────────────────────────────────────────────────────

interface StepperProps {
  steps: string[];
  current: number; // 0-indexed
}

export function Stepper({ steps, current }: StepperProps) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((step, i) => {
        const done   = i < current;
        const active = i === current;
        return (
          <React.Fragment key={i}>
            <div className="flex flex-col items-center gap-1 flex-shrink-0">
              <div
                className={cn(
                  'size-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all',
                  done   ? 'bg-[var(--accent)] text-white' :
                  active ? 'border-2 border-[var(--accent)] text-[var(--accent)] bg-transparent' :
                           'border border-[var(--border)] text-[var(--text-muted)] bg-transparent'
                )}
              >
                {done ? <Check size={13} /> : i + 1}
              </div>
              <span
                className={cn(
                  'text-xs font-medium whitespace-nowrap',
                  active ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'
                )}
              >
                {step}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                className={cn(
                  'flex-1 h-px mx-3 mb-4 transition-colors',
                  i < current ? 'bg-[var(--accent)]' : 'bg-[var(--border)]'
                )}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Toggle ──────────────────────────────────────────────────────────────────

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  description?: string;
}

export function Toggle({ checked, onChange, label, description }: ToggleProps) {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent',
          'transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2',
          'focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1',
          'focus-visible:ring-offset-[var(--background)]',
          checked ? 'bg-[var(--accent)]' : 'bg-[var(--border)]'
        )}
      >
        <span
          className={cn(
            'pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform duration-150',
            checked ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </button>
      {(label || description) && (
        <label htmlFor={id} className="cursor-pointer space-y-0.5">
          {label && <p className="text-sm font-medium text-[var(--text-primary)]">{label}</p>}
          {description && <p className="text-xs text-[var(--text-muted)]">{description}</p>}
        </label>
      )}
    </div>
  );
}

// ─── InlineInput (copy URL field) ─────────────────────────────────────────────

export function InlineCopyField({ value, label }: { value: string; label?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="space-y-1.5">
      {label && <p className="text-xs text-[var(--text-muted)]">{label}</p>}
      <div className="flex gap-2 items-center">
        <input
          ref={ref}
          readOnly
          value={value}
          onClick={() => ref.current?.select()}
          className="flex-1 rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-xs text-[var(--text-secondary)] font-mono focus:outline-none"
        />
        <button
          onClick={copy}
          className="shrink-0 flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)] transition-all duration-150"
        >
          {copied ? <Check size={12} className="text-[var(--emerald-chip-text)]" /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}
