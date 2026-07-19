/**
 * /console/requisitions/new — Requisition Builder.
 * Configures an AI-conducted screening interview: core details (with
 * autocomplete against known titles/domains), role context + sample questions,
 * skill chips, interviewer tone, a drag-and-drop screening form builder that
 * renders a candidate-facing preview, and weighted assessment rubrics.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  Check,
  CheckSquare,
  CircleDot,
  Copy,
  Globe,
  GripVertical,
  ListChecks,
  Plus,
  Rocket,
  Settings2,
  SlidersHorizontal,
  Trash2,
  Type,
  Upload,
  X,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useToast, Spinner } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';
import InvitePanel from './InvitePanel';
import { copyToClipboard, getInterviewUrl } from './requisitionData';
import {
  consoleApi,
  useCatalog,
  useConsoleRequisition,
  useConsoleUsage,
  type ConsoleRequisitionDetailWire,
  type ConsoleRequisitionIn,
} from '../../lib/consoleApi';
import { useQueryClient } from '@tanstack/react-query';

/* -------------------------------------------------------------------------- */
/*  Types & constants                                                         */
/* -------------------------------------------------------------------------- */

type Tone = 'conversational' | 'friendly' | 'technical' | 'structured' | 'bar_raiser';

const TONE_OPTIONS: { value: Tone; label: string; description: string }[] = [
  {
    value: 'conversational',
    label: 'Conversational',
    description: 'Natural, relaxed pacing for early screens.',
  },
  {
    value: 'friendly',
    label: 'Friendly & Encouraging',
    description: 'Warm prompts for junior or high-volume roles.',
  },
  {
    value: 'technical',
    label: 'Technical / Strict',
    description: 'Rigorous follow-ups for senior technical screens.',
  },
  {
    value: 'structured',
    label: 'Formal & Structured',
    description: 'Consistent question flow for easy comparison.',
  },
  {
    value: 'bar_raiser',
    label: 'Challenging / Bar-Raiser',
    description: 'Probing style for leadership and bar-raiser loops.',
  },
];

type FieldType =
  | 'text' | 'textarea' | 'multiple_choice' | 'multi_select'
  | 'range' | 'date' | 'file' | 'social';

interface ScreeningField {
  id: string;
  type: FieldType;
  label: string;
  placeholder: string;
  required: boolean;
  options: string[]; // multiple_choice / multi_select only
}

interface RubricCriterion {
  id: string;
  name: string;
  description: string;
  weight: number;
}

interface SampleQuestion {
  id: string;
  text: string;
}

const FIELD_TYPES: { type: FieldType; label: string; icon: typeof Type }[] = [
  { type: 'text',            label: 'Text Field',       icon: Type },
  { type: 'textarea',        label: 'Text Area',        icon: ListChecks },
  { type: 'multiple_choice', label: 'Multiple Choice',  icon: CircleDot },
  { type: 'multi_select',    label: 'Multi-Select',     icon: CheckSquare },
  { type: 'range',           label: 'Range (1-10)',     icon: SlidersHorizontal },
  { type: 'date',            label: 'Date Picker',      icon: Calendar },
  { type: 'file',            label: 'File Upload',      icon: Upload },
  { type: 'social',          label: 'Social Scraper',   icon: Globe },
];

const FIELD_LABELS: Record<FieldType, string> = {
  text: 'Text Field', textarea: 'Text Area', multiple_choice: 'Multiple Choice',
  multi_select: 'Multi-Select', range: 'Range (1-10)', date: 'Date Picker',
  file: 'File Upload', social: 'Social Scraper',
};

const FIELD_DEFAULTS: Record<FieldType, { label: string; placeholder: string }> = {
  text:            { label: 'Short answer',                 placeholder: 'Type your answer…' },
  textarea:        { label: 'Long answer',                  placeholder: 'Write a few sentences…' },
  multiple_choice: { label: 'Pick one option',              placeholder: '' },
  multi_select:    { label: 'Select all that apply',        placeholder: '' },
  range:           { label: 'Rate on a scale of 1–10',      placeholder: '' },
  date:            { label: 'Pick a date',                  placeholder: '' },
  file:            { label: 'Upload a file',                placeholder: 'PDF or DOCX, up to 10 MB' },
  social:          { label: 'Link a social profile',        placeholder: 'https://linkedin.com/in/…' },
};

const CHOICE_TYPES: FieldType[] = ['multiple_choice', 'multi_select'];
const PLACEHOLDER_TYPES: FieldType[] = ['text', 'textarea', 'file', 'social'];

let idCounter = 0;
const nextId = () => `el-${++idCounter}`;

// The backend echoes end_date as a UTC ISO string (e.g. "...T23:59:59+00:00"),
// but <input type="datetime-local"> only accepts a naive "YYYY-MM-DDTHH:mm"
// value — strip the offset/seconds rather than converting timezones, so the
// digits round-trip unchanged through save/reload.
const toDatetimeLocal = (iso: string | null | undefined): string =>
  iso ? iso.replace(/(Z|[+-]\d{2}:\d{2})$/, '').slice(0, 16) : '';

const makeField = (type: FieldType): ScreeningField => ({
  id: nextId(),
  type,
  label: FIELD_DEFAULTS[type].label,
  placeholder: FIELD_DEFAULTS[type].placeholder,
  required: false,
  options: CHOICE_TYPES.includes(type) ? ['Option 1', 'Option 2', 'Option 3'] : [],
});

/* -------------------------------------------------------------------------- */
/*  Shared field shell                                                        */
/* -------------------------------------------------------------------------- */

function FieldLabel({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label className="label-mono text-on-surface-variant">
      {children}
      {required && <span className="text-error"> *</span>}
    </label>
  );
}

function inputClasses(hasError: boolean) {
  return cn(
    'w-full border bg-surface-container-lowest px-3 py-2.5 text-body-md text-on-surface',
    'placeholder:text-on-surface-variant focus:outline-none transition-colors duration-150',
    hasError ? 'border-error' : 'border-outline-variant focus:border-primary-container',
  );
}

/* -------------------------------------------------------------------------- */
/*  Autocomplete input (single value)                                         */
/* -------------------------------------------------------------------------- */

interface AutocompleteInputProps {
  value: string;
  onChange: (value: string) => void;
  suggestions: string[];
  onCreate: (value: string) => void;
  placeholder?: string;
  hasError?: boolean;
  onBlur?: () => void;
}

function AutocompleteInput({
  value, onChange, suggestions, onCreate, placeholder, hasError, onBlur,
}: AutocompleteInputProps) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const query = value.trim().toLowerCase();
  const matches = suggestions.filter(s => s.toLowerCase().includes(query));
  const hasExact = suggestions.some(s => s.toLowerCase() === query);
  const createValue = !hasExact && query.length > 0 ? value.trim() : null;
  const rowCount = matches.length + (createValue ? 1 : 0);
  const active = Math.min(highlight, rowCount - 1);

  const selectRow = (index: number) => {
    if (index < matches.length) {
      onChange(matches[index]);
    } else if (createValue) {
      onCreate(createValue);
      onChange(createValue);
    }
    setOpen(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (open) setHighlight(h => Math.min(h + 1, rowCount - 1));
      else setOpen(true);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && open && rowCount > 0) {
      e.preventDefault();
      selectRow(active);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); setHighlight(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => { setOpen(false); onBlur?.(); }}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={inputClasses(!!hasError)}
      />
      {open && rowCount > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-20 border border-outline-variant bg-surface shadow-xl max-h-60 overflow-y-auto">
          {matches.map((s, i) => (
            <button
              key={s}
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => selectRow(i)}
              onMouseEnter={() => setHighlight(i)}
              className={cn(
                'w-full text-left px-3 py-2 text-body-md transition-colors duration-75',
                i === active ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
              )}
            >
              {s}
            </button>
          ))}
          {createValue && (
            <button
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => selectRow(matches.length)}
              onMouseEnter={() => setHighlight(matches.length)}
              className={cn(
                'w-full text-left px-3 py-2 text-body-md flex items-center gap-2 transition-colors duration-75',
                matches.length > 0 && 'border-t border-outline-variant',
                matches.length === active ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
              )}
            >
              <Plus size={14} className="shrink-0" />
              Create “{createValue}”
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Autocomplete chips (multi value)                                          */
/* -------------------------------------------------------------------------- */

interface ChipAutocompleteProps {
  value: string[];
  onChange: (value: string[]) => void;
  suggestions: string[];
  onCreate: (value: string) => void;
  placeholder?: string;
  hasError?: boolean;
  onBlur?: () => void;
}

function ChipAutocomplete({
  value, onChange, suggestions, onCreate, placeholder, hasError, onBlur,
}: ChipAutocompleteProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [input, setInput] = useState('');
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const query = input.trim().toLowerCase();
  const selectedLower = value.map(v => v.toLowerCase());
  const available = suggestions.filter(s => !selectedLower.includes(s.toLowerCase()));
  const matches = available.filter(s => s.toLowerCase().includes(query));
  const hasExact = suggestions.some(s => s.toLowerCase() === query);
  const createValue = !hasExact && query.length > 0 ? input.trim() : null;
  const rowCount = matches.length + (createValue ? 1 : 0);
  const active = Math.min(highlight, rowCount - 1);

  const addChip = (chip: string) => {
    if (!value.some(v => v.toLowerCase() === chip.toLowerCase())) {
      onChange([...value, chip]);
    }
    setInput('');
    setHighlight(0);
  };

  const selectRow = (index: number) => {
    if (index < matches.length) {
      addChip(matches[index]);
    } else if (createValue) {
      onCreate(createValue);
      addChip(createValue);
    }
  };

  // Typed-but-unconfirmed text would otherwise sit in the input looking like
  // a saved skill while never reaching the payload — commit it as a chip.
  const commitPending = () => {
    const pending = input.trim();
    if (!pending) return;
    const canonical = suggestions.find(s => s.toLowerCase() === query);
    if (canonical) {
      addChip(canonical);
    } else {
      onCreate(pending);
      addChip(pending);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (open) setHighlight(h => Math.min(h + 1, rowCount - 1));
      else setOpen(true);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight(h => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (open && rowCount > 0) {
        selectRow(active);
      } else {
        commitPending();
      }
    } else if (e.key === 'Backspace' && input === '' && value.length > 0) {
      onChange(value.slice(0, -1));
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="relative">
      <div
        onClick={() => inputRef.current?.focus()}
        className={cn(
          'flex flex-wrap items-center gap-2 border bg-surface-container-lowest px-3 py-2 min-h-[46px] cursor-text',
          'transition-colors duration-150',
          hasError ? 'border-error' : 'border-outline-variant focus-within:border-primary-container',
        )}
      >
        {value.map(chip => (
          <span
            key={chip}
            className="flex items-center gap-1.5 pl-2 pr-1 py-1 border border-primary-container bg-primary-container/10 text-primary-fixed-dim label-mono"
          >
            {chip}
            <button
              type="button"
              onClick={() => onChange(value.filter(v => v !== chip))}
              className="p-0.5 hover:text-error transition-colors duration-150"
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => { setInput(e.target.value); setOpen(true); setHighlight(0); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { setOpen(false); commitPending(); onBlur?.(); }}
          onKeyDown={handleKeyDown}
          placeholder={value.length === 0 ? placeholder : undefined}
          className="flex-1 min-w-[160px] bg-transparent border-none p-0 py-1 text-body-md text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:ring-0"
        />
      </div>
      {open && rowCount > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1 z-20 border border-outline-variant bg-surface shadow-xl max-h-60 overflow-y-auto">
          {matches.map((s, i) => (
            <button
              key={s}
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => selectRow(i)}
              onMouseEnter={() => setHighlight(i)}
              className={cn(
                'w-full text-left px-3 py-2 text-body-md transition-colors duration-75',
                i === active ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
              )}
            >
              {s}
            </button>
          ))}
          {createValue && (
            <button
              type="button"
              onMouseDown={e => e.preventDefault()}
              onClick={() => selectRow(matches.length)}
              onMouseEnter={() => setHighlight(matches.length)}
              className={cn(
                'w-full text-left px-3 py-2 text-body-md flex items-center gap-2 transition-colors duration-75',
                matches.length > 0 && 'border-t border-outline-variant',
                matches.length === active ? 'bg-primary-container/10 text-primary-fixed-dim' : 'text-on-surface',
              )}
            >
              <Plus size={14} className="shrink-0" />
              Create “{createValue}”
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Candidate-facing field preview                                            */
/* -------------------------------------------------------------------------- */

function FieldPreview({ field }: { field: ScreeningField }) {
  const options = field.options.map(o => o.trim()).filter(Boolean);

  return (
    <div className="pointer-events-none select-none flex flex-col gap-2">
      <FieldLabel required={field.required}>{field.label || 'Untitled question'}</FieldLabel>

      {field.type === 'text' && (
        <input type="text" readOnly tabIndex={-1} placeholder={field.placeholder} className={inputClasses(false)} />
      )}

      {field.type === 'textarea' && (
        <textarea readOnly tabIndex={-1} placeholder={field.placeholder} className={cn(inputClasses(false), 'h-24 resize-none')} />
      )}

      {field.type === 'multiple_choice' && (
        <div className="flex flex-col gap-2.5">
          {options.map(opt => (
            <div key={opt} className="flex items-center gap-3">
              <span className="size-4 rounded-full border border-outline-variant shrink-0" />
              <span className="text-body-md text-on-surface">{opt}</span>
            </div>
          ))}
        </div>
      )}

      {field.type === 'multi_select' && (
        <div className="flex flex-col gap-2.5">
          {options.map(opt => (
            <div key={opt} className="flex items-center gap-3">
              <span className="size-4 border border-outline-variant shrink-0" />
              <span className="text-body-md text-on-surface">{opt}</span>
            </div>
          ))}
        </div>
      )}

      {field.type === 'range' && (
        <div className="flex items-center gap-4 py-2">
          <span className="label-mono text-on-surface-variant">1</span>
          <div className="relative flex-1 h-1 bg-outline-variant">
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 size-4 rounded-full bg-primary-container" />
          </div>
          <span className="label-mono text-on-surface-variant">10</span>
        </div>
      )}

      {field.type === 'date' && (
        <input type="date" readOnly tabIndex={-1} className={inputClasses(false)} />
      )}

      {field.type === 'file' && (
        <div className="border border-dashed border-outline-variant p-6 flex flex-col items-center gap-2 text-on-surface-variant">
          <Upload size={20} />
          <span className="text-body-md">Click to upload or drag a file here</span>
          {field.placeholder && <span className="label-mono">{field.placeholder}</span>}
        </div>
      )}

      {field.type === 'social' && (
        <div className="relative">
          <Globe size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
          <input type="text" readOnly tabIndex={-1} placeholder={field.placeholder} className={cn(inputClasses(false), 'pl-10')} />
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

type DragPayload = { kind: 'new'; type: FieldType } | { kind: 'move'; id: string };

export default function RequisitionBuilder() {
  const { requisitionId } = useParams<{ requisitionId: string }>();
  const detail = useConsoleRequisition(requisitionId);
  const catalog = useCatalog();

  if ((requisitionId && !detail.data) || !catalog.data) {
    return (
      <ConsoleLayout>
        <div className="p-8">
          <p className="label-mono text-on-surface-variant">
            {detail.isError ? 'Requisition not found.' : 'Loading requisition builder…'}
          </p>
        </div>
      </ConsoleLayout>
    );
  }

  return (
    <BuilderForm
      key={requisitionId ?? 'new'}
      existing={detail.data ?? null}
      dbJobTitles={catalog.data.job_titles}
      dbDomains={catalog.data.domains}
      dbSkills={catalog.data.skills}
    />
  );
}

function BuilderForm({
  existing,
  dbJobTitles,
  dbDomains,
  dbSkills,
}: {
  existing: ConsoleRequisitionDetailWire | null;
  dbJobTitles: string[];
  dbDomains: string[];
  dbSkills: string[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const isEditing = !!existing;
  // Free-plan quota: a new requisition can't be created past the limit
  // (deploying an existing one doesn't add to the count). Server enforces
  // the same rule; this just fails fast with the upgrade message.
  const { data: usage } = useConsoleUsage();
  const atRequisitionLimit =
    !isEditing && !!usage && usage.requisitions_used >= usage.requisitions_limit;
  const currentStatus = existing?.status ?? 'draft';
  const interviewUrl = existing?.invite_token ? getInterviewUrl(existing.invite_token) : null;
  const [copiedInterviewUrl, setCopiedInterviewUrl] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deployState, setDeployState] = useState<'idle' | 'processing' | 'success'>('idle');
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleCloseSplash = useCallback(() => {
    setDeployState('idle');
    navigate('/console/requisitions');
  }, [navigate]);

  useEffect(() => {
    if (deployState !== 'success') return;
    const timer = setTimeout(() => {
      handleCloseSplash();
    }, 6000);
    return () => clearTimeout(timer);
  }, [deployState, handleCloseSplash]);

  const [jobTitle, setJobTitle]   = useState(existing?.title ?? '');
  const [domain, setDomain]       = useState(existing?.domain ?? '');
  const [objective, setObjective] = useState(existing?.objective ?? '');
  const [skills, setSkills]       = useState<string[]>(existing?.technical_requirements ?? []);
  const [tone, setTone]           = useState<Tone>((existing?.tone as Tone) ?? 'technical');
  const [endDate, setEndDate]     = useState(toDatetimeLocal(existing?.end_date));
  const [durationMinutes, setDurationMinutes] = useState<number>(existing?.duration_minutes ?? 30);
  const [proctoringEnabled, setProctoringEnabled] = useState(existing?.proctoring_enabled ?? true);
  const [inviteOnly, setInviteOnly] = useState(existing?.invite_only ?? false);
  const [touched, setTouched]     = useState<Record<string, boolean>>({});
  const [attempted, setAttempted] = useState(false);

  // Catalog-backed autocomplete lists; values a user "creates" are appended
  // for the session and persisted server-side on deploy/save.
  const [jobTitleDb, setJobTitleDb] = useState<string[]>(dbJobTitles);
  const [domainDb, setDomainDb]     = useState<string[]>(dbDomains);
  const [skillDb, setSkillDb]       = useState<string[]>(dbSkills);

  const [sampleQuestions, setSampleQuestions] = useState<SampleQuestion[]>(
    (existing?.sample_questions ?? []).map(q => ({ id: nextId(), text: q.text })),
  );

  const [fields, setFields] = useState<ScreeningField[]>(
    (existing?.screening_fields ?? []).map(f => ({
      id: nextId(),
      type: f.type,
      label: f.label,
      placeholder: f.placeholder,
      required: f.required,
      options: f.options,
    })),
  );
  const [expandedFieldId, setExpandedFieldId] = useState<string | null>(null);
  const [dragging, setDragging] = useState<DragPayload | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  const [criteria, setCriteria] = useState<RubricCriterion[]>(
    existing?.rubric.length
      ? existing.rubric.map(c => ({
          id: nextId(),
          name: c.name,
          description: c.description,
          weight: c.weight,
        }))
      : [
          { id: nextId(), name: 'Technical Skill',  description: '', weight: 50 },
          { id: nextId(), name: 'Communication',    description: '', weight: 30 },
          { id: nextId(), name: 'Problem Solving',  description: '', weight: 20 },
        ],
  );

  const totalWeight = useMemo(() => criteria.reduce((sum, c) => sum + (c.weight || 0), 0), [criteria]);

  const errors = useMemo(() => {
    const list: string[] = [];
    if (!jobTitle.trim())    list.push('Job title is required.');
    if (!domain.trim())      list.push('Domain is required.');
    if (skills.length === 0) list.push('Add at least one must-have skill.');
    if (criteria.length < 3) list.push('Add at least 3 rubric criteria.');
    if (totalWeight !== 100) list.push('Rubric weightage must total 100%.');
    if (criteria.some(c => !c.name.trim())) {
      list.push('All rubric criteria must have a title.');
    }
    if (criteria.some(c => !c.description.trim())) {
      list.push('All rubric criteria must have a description.');
    }
    if (criteria.some(c => !c.weight || c.weight <= 0)) {
      list.push('Every rubric criterion needs a weight above 0%.');
    }
    return list;
  }, [jobTitle, domain, skills, criteria, totalWeight]);

  // Live comes from the saved status; draft vs offline tracks the current
  // form's validation state, so the chip updates as errors are fixed.
  const effectiveStatus: 'live' | 'draft' | 'offline' =
    currentStatus === 'open' ? 'live' : errors.length > 0 ? 'draft' : 'offline';

  const showError = (field: string) => (touched[field] || attempted);
  const markTouched = (field: string) => setTouched(t => ({ ...t, [field]: true }));

  /* ── screening form field ops ─────────────────────────────────────────── */

  const insertField = (type: FieldType, at: number) => {
    const field = makeField(type);
    setFields(f => {
      const next = [...f];
      next.splice(at, 0, field);
      return next;
    });
    setExpandedFieldId(field.id);
  };

  const moveField = (id: string, to: number) => {
    setFields(f => {
      const from = f.findIndex(x => x.id === id);
      if (from === -1) return f;
      const target = from < to ? to - 1 : to;
      if (target === from) return f;
      const next = [...f];
      const [item] = next.splice(from, 1);
      next.splice(target, 0, item);
      return next;
    });
  };

  const removeField = (id: string) => {
    setFields(f => f.filter(x => x.id !== id));
    setExpandedFieldId(cur => (cur === id ? null : cur));
  };

  const updateField = (id: string, patch: Partial<ScreeningField>) =>
    setFields(f => f.map(x => (x.id === id ? { ...x, ...patch } : x)));

  const endDrag = () => {
    setDragging(null);
    setDropIndex(null);
  };

  const handleCanvasDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (!dragging) return;
    const at = dropIndex ?? fields.length;
    if (dragging.kind === 'new') insertField(dragging.type, at);
    else moveField(dragging.id, at);
    endDrag();
  };

  /* ── sample question ops ──────────────────────────────────────────────── */

  const addQuestion = () => setSampleQuestions(q => [...q, { id: nextId(), text: '' }]);
  const removeQuestion = (id: string) => setSampleQuestions(q => q.filter(x => x.id !== id));
  const updateQuestion = (id: string, text: string) =>
    setSampleQuestions(q => q.map(x => (x.id === id ? { ...x, text } : x)));

  /* ── rubric ops ───────────────────────────────────────────────────────── */

  const addCriterion = () =>
    setCriteria(c => [...c, { id: nextId(), name: '', description: '', weight: 0 }]);
  const removeCriterion = (id: string) => setCriteria(c => c.filter(x => x.id !== id));
  const updateCriterion = (id: string, patch: Partial<RubricCriterion>) =>
    setCriteria(c => c.map(x => (x.id === id ? { ...x, ...patch } : x)));

  /* ── actions ──────────────────────────────────────────────────────────── */

  const buildPayload = (deploy: boolean): ConsoleRequisitionIn => ({
    title: jobTitle.trim(),
    domain: domain.trim(),
    objective: objective.trim(),
    skills,
    tone,
    end_date: endDate || null,
    proctoring_enabled: proctoringEnabled,
    invite_only: inviteOnly,
    duration_minutes: Math.max(15, Math.min(90, Math.round(durationMinutes) || 30)),
    sample_questions: sampleQuestions
      .filter(q => q.text.trim())
      .map(q => ({ id: q.id, text: q.text.trim() })),
    screening_fields: fields.map(f => ({
      id: f.id,
      type: f.type,
      label: f.label,
      placeholder: f.placeholder,
      required: f.required,
      options: f.options,
    })),
    rubric: criteria.map(c => ({
      id: c.id,
      name: c.name,
      description: c.description,
      weight: c.weight,
    })),
    deploy,
  });

  const submit = async (deploy: boolean) => {
    setSaving(true);
    try {
      const payload = buildPayload(deploy);
      if (isEditing && existing) {
        await consoleApi.updateRequisition(existing.id, payload);
      } else {
        await consoleApi.createRequisition(payload);
      }
      await queryClient.invalidateQueries({ queryKey: ['console'] });
      if (deploy) {
        setDeployState('success');
      } else {
        toast(
          errors.length > 0
            ? `"${jobTitle || 'Untitled requisition'}" saved as draft.`
            : `"${jobTitle}" saved as offline.`,
          'info',
        );
        navigate('/console/requisitions');
      }
    } catch (err) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        'Saving the requisition failed. Please try again.';
      toast(message, 'error');
      if (deploy) {
        setDeployState('idle');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDeploy = () => {
    if (atRequisitionLimit) {
      toast('Please upgrade to deploy more interviews.', 'error');
      return;
    }
    if (errors.length > 0) {
      setAttempted(true);
      toast('Resolve the errors below before deploying.', 'error');
      return;
    }
    if (saving) return;
    setDeployState('processing');
    void submit(true);
  };

  const handleSaveOffline = () => {
    if (atRequisitionLimit) {
      toast(
        `Your free plan allows ${usage?.requisitions_limit ?? 5} requisitions. Please upgrade to create more.`,
        'error',
      );
      return;
    }
    if (!jobTitle.trim() || !domain.trim()) {
      setAttempted(true);
      toast('Job title and domain are required even for drafts.', 'error');
      return;
    }
    if (saving) return;
    void submit(false);
  };

  const handleConfirmDelete = async () => {
    if (!existing || deleting) return;
    setDeleting(true);
    try {
      await consoleApi.deleteRequisition(existing.id);
      await queryClient.invalidateQueries({ queryKey: ['console'] });
      toast(`"${existing.title}" was deleted.`, 'info');
      navigate('/console/requisitions');
    } catch (err) {
      const message =
        (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
        'Deleting the requisition failed. Please try again.';
      toast(message, 'error');
      setDeleting(false);
      setConfirmingDelete(false);
    }
  };

  const handleCopyInterviewUrl = async () => {
    if (!interviewUrl) return;
    await copyToClipboard(interviewUrl);
    setCopiedInterviewUrl(true);
    setTimeout(() => setCopiedInterviewUrl(false), 1800);
  };

  const skillsInvalid = showError('skills') && skills.length === 0;

  return (
    <ConsoleLayout>
      {/* Header */}
      <header className="h-16 border-b border-outline-variant bg-surface flex items-center justify-between px-8 sticky top-0 z-30">
        <span className="label-mono text-on-surface-variant m-[1em]">Requisition Builder</span>
        <span className="label-mono text-primary-fixed-dim">
          {jobTitle.trim() || 'Untitled Requisition'}
        </span>
      </header>

      {/* Content */}
      <div className="flex-1 p-4">
        <div className="w-full max-w-[1440px] flex flex-col border border-outline-variant">
          {/* Title block */}
          <div className="p-5 border-b border-outline-variant bg-surface-container-lowest">
            <div className="mb-4 flex items-center justify-between">
              <Link
                to="/console/requisitions"
                className="h-9 px-3 border border-outline-variant text-on-surface-variant label-mono flex items-center gap-2 hover:bg-surface-container hover:text-on-surface transition-colors duration-150"
              >
                <ArrowLeft size={14} />
                ALL REQUISITIONS
              </Link>
              {effectiveStatus === 'live' && (
                <div
                  className="relative group px-3 py-1 label-mono text-xs flex items-center gap-2 select-none border border-[var(--emerald-chip-text)]/20 bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)] shrink-0 cursor-help"
                >
                  <span className="size-2 bg-[var(--emerald-chip-text)] blink" />
                  LIVE

                  {/* Tooltip Overlay */}
                  <div className="absolute top-full right-0 mt-3 hidden group-hover:block bg-surface-container-high border border-outline-variant text-on-surface text-sm rounded-lg p-3 shadow-lg z-50 w-80 pointer-events-none normal-case tracking-normal">
                    <p className="font-semibold text-body-md text-primary-fixed-dim flex items-center gap-1.5 mb-1">
                      <Check size={14} />
                      Live State
                    </p>
                    <p className="text-on-surface-variant text-sm">
                      Requisition is Live. Users should be able to land on interview page and attempt the interview.
                    </p>
                    {/* Arrow */}
                    <div className="absolute bottom-full right-6 w-3 h-3 bg-surface-container-high border-l border-t border-outline-variant rotate-45 -mb-1.5" />
                  </div>
                </div>
              )}
              {effectiveStatus === 'draft' && (
                <div
                  className="relative group px-3 py-1 label-mono text-xs flex items-center gap-2 select-none border border-[var(--amber-chip-text)]/20 bg-[var(--amber-chip-bg)] text-[var(--amber-chip-text)] shrink-0 cursor-help"
                >
                  <span className="size-2 bg-[var(--amber-chip-text)]" />
                  DRAFT

                  {/* Tooltip Overlay */}
                  <div className="absolute top-full right-0 mt-3 hidden group-hover:block bg-surface-container-high border border-outline-variant text-on-surface text-sm rounded-lg p-3 shadow-lg z-50 w-80 pointer-events-none normal-case tracking-normal">
                    <p className="font-semibold text-body-md mb-2 text-error flex items-center gap-1.5">
                      <AlertTriangle size={14} />
                      Necessary steps to publish:
                    </p>
                    <ul className="list-disc pl-4 space-y-1.5 text-on-surface-variant text-sm">
                      {errors.map((err, i) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                    {/* Arrow */}
                    <div className="absolute bottom-full right-6 w-3 h-3 bg-surface-container-high border-l border-t border-outline-variant rotate-45 -mb-1.5" />
                  </div>
                </div>
              )}
              {effectiveStatus === 'offline' && (
                <div
                  className="relative group px-3 py-1 label-mono text-xs flex items-center gap-2 select-none border border-outline-variant bg-surface-container-lowest text-on-surface-variant shrink-0 cursor-help"
                >
                  <span className="size-2 bg-outline" />
                  OFFLINE

                  {/* Tooltip Overlay */}
                  <div className="absolute top-full right-0 mt-3 hidden group-hover:block bg-surface-container-high border border-outline-variant text-on-surface text-sm rounded-lg p-3 shadow-lg z-50 w-80 pointer-events-none normal-case tracking-normal">
                    <p className="font-semibold text-body-md text-on-surface flex items-center gap-1.5 mb-1">
                      <span className="size-2 bg-outline rounded-full" />
                      Offline State
                    </p>
                    <p className="text-on-surface-variant text-sm">
                      All checks passed, but the requisition is not published yet. Deploy the
                      interview to take it live.
                    </p>
                    {/* Arrow */}
                    <div className="absolute bottom-full right-6 w-3 h-3 bg-surface-container-high border-l border-t border-outline-variant rotate-45 -mb-1.5" />
                  </div>
                </div>
              )}
            </div>
            <div className="flex flex-col xl:flex-row xl:items-start justify-between gap-6">
              <div className="flex flex-col gap-2">
                <h1 className="font-display text-headline-lg text-on-surface">
                  {isEditing ? 'Edit Requisition' : 'New Requisition'}
                </h1>
                <p className="text-body-md text-on-surface-variant max-w-[80ch]">
                  Define the role, required skills, candidate screening questions, AI interviewer style,
                  and scoring rubric in one structured setup. When deployed, this requisition becomes
                  a shareable candidate interview link that collects form responses first, then guides
                  candidates into the voice interview and returns scored evidence for review.
                </p>
              </div>
              {interviewUrl && (
                <div className="flex flex-col gap-1.5 w-full xl:w-80 shrink-0">
                  <span className="label-mono text-[10px] text-on-surface-variant">Interview Link</span>
                  <div className="flex items-center border border-outline-variant bg-surface-container-lowest overflow-hidden transition-colors focus-within:border-primary-container">
                    {/* Read-only URL display */}
                    <div className="flex-1 px-3 py-2 text-xs font-mono text-on-surface-variant truncate select-all" title={interviewUrl}>
                      {interviewUrl}
                    </div>
                    {/* Copy Button */}
                    <button
                      type="button"
                      onClick={handleCopyInterviewUrl}
                      className={cn(
                        "h-9 px-3.5 border-l border-outline-variant label-mono flex items-center gap-1.5 transition-colors duration-150 shrink-0",
                        copiedInterviewUrl 
                          ? "bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)] border-[var(--emerald-chip-text)]/20" 
                          : "bg-primary-container text-on-primary hover:bg-transparent hover:text-primary-fixed-dim"
                      )}
                    >
                      {copiedInterviewUrl ? (
                        <>
                          COPIED
                          <Check size={13} />
                        </>
                      ) : (
                        <>
                          COPY
                          <Copy size={13} />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 01. Core Details */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">01. Core Details</h2>
              <span className="label-mono text-primary-fixed-dim uppercase px-2 py-1 border border-primary-container bg-primary-container/10">
                Required
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div className="flex flex-col gap-2">
                <FieldLabel required>Job Title</FieldLabel>
                <AutocompleteInput
                  value={jobTitle}
                  onChange={setJobTitle}
                  suggestions={jobTitleDb}
                  onCreate={v => setJobTitleDb(db => [...db, v])}
                  onBlur={() => markTouched('jobTitle')}
                  placeholder="e.g. Senior Frontend Engineer"
                  hasError={showError('jobTitle') && !jobTitle.trim()}
                />
                {showError('jobTitle') && !jobTitle.trim() && (
                  <span className="label-mono text-error normal-case tracking-normal">Job title is required.</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <FieldLabel required>Domain</FieldLabel>
                <AutocompleteInput
                  value={domain}
                  onChange={setDomain}
                  suggestions={domainDb}
                  onCreate={v => setDomainDb(db => [...db, v])}
                  onBlur={() => markTouched('domain')}
                  placeholder="e.g. Engineering"
                  hasError={showError('domain') && !domain.trim()}
                />
                {showError('domain') && !domain.trim() && (
                  <span className="label-mono text-error normal-case tracking-normal">Domain is required.</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <FieldLabel>Close Date (Optional)</FieldLabel>
                <input
                  type="datetime-local"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className={inputClasses(false)}
                />
                <span className="text-body-md text-on-surface-variant">
                  The interview link automatically goes offline at this date and time.
                  Leave empty to keep it open until you pause or close the requisition.
                </span>
              </div>
              <div className="flex flex-col gap-2">
                <FieldLabel>Interview Duration (Minutes)</FieldLabel>
                <input
                  type="number"
                  min={15}
                  max={90}
                  step={5}
                  value={Number.isFinite(durationMinutes) ? durationMinutes : ''}
                  onChange={e => setDurationMinutes(e.target.valueAsNumber)}
                  onBlur={() =>
                    setDurationMinutes(v =>
                      Math.max(15, Math.min(90, Math.round(Number.isFinite(v) ? v : 30))),
                    )
                  }
                  className={inputClasses(false)}
                />
                <span className="text-body-md text-on-surface-variant">
                  The AI interviewer paces its questions to fit this window and ends the
                  interview when time is up. Between 15 and 90 minutes; default 30.
                </span>
              </div>
            </div>
          </div>

          {/* 02. Role Context */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">02. Role Context</h2>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)] gap-5">
              <div className="flex flex-col gap-2">
                <FieldLabel>Ideal Candidate & Role Objective</FieldLabel>
                <textarea
                  value={objective}
                  onChange={e => setObjective(e.target.value)}
                  placeholder="e.g. We need a hands-on engineer who has scaled a consumer product past a million users, communicates clearly with non-technical stakeholders, and can own our checkout flow end-to-end within the first quarter..."
                  className={cn(inputClasses(false), 'h-40 resize-none')}
                />
              </div>

              <div className="flex flex-col gap-3">
                <FieldLabel>Sample Questions (Optional)</FieldLabel>
                {sampleQuestions.map((q, i) => (
                  <div key={q.id} className="flex items-center gap-3">
                    <span className="label-mono text-on-surface-variant w-8 shrink-0">Q{i + 1}</span>
                    <input
                      type="text"
                      value={q.text}
                      onChange={e => updateQuestion(q.id, e.target.value)}
                      placeholder="e.g. Walk me through a system you designed end-to-end. What would you change today?"
                      className={inputClasses(false)}
                    />
                    <button
                      type="button"
                      onClick={() => removeQuestion(q.id)}
                      className="text-error hover:bg-error/10 p-2 transition-colors duration-150 shrink-0"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={addQuestion}
                  className="self-start flex items-center gap-2 px-4 py-2 border border-outline-variant text-on-surface-variant label-mono hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150"
                >
                  <Plus size={16} />
                  Add Sample Question
                </button>
              </div>
            </div>
          </div>

          {/* 03. Technical Requirements */}
          <div
            className={cn(
              'p-5 border-b border-outline-variant',
              skillsInvalid && 'bg-surface/50 border-l-[4px] border-l-error',
            )}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">03. Technical Requirements</h2>
              {skillsInvalid ? (
                <span className="label-mono text-error uppercase flex items-center gap-1">
                  <AlertTriangle size={14} /> Needs Attention
                </span>
              ) : (
                <span className="label-mono text-primary-fixed-dim uppercase px-2 py-1 border border-primary-container bg-primary-container/10">
                  Required
                </span>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <FieldLabel required>Must-Have Skills</FieldLabel>
              <ChipAutocomplete
                value={skills}
                onChange={setSkills}
                suggestions={skillDb}
                onCreate={v => setSkillDb(db => [...db, v])}
                onBlur={() => markTouched('skills')}
                placeholder="Start typing to search skills — e.g. React, TypeScript, GraphQL…"
                hasError={skillsInvalid}
              />
              <span className="text-body-md text-on-surface-variant">
                Pick existing skills or type a new one and press Enter.
              </span>
              {skillsInvalid && (
                <span className="label-mono text-error normal-case tracking-normal">
                  Add at least one must-have skill.
                </span>
              )}
            </div>
          </div>

          {/* 04. Interviewer Tone */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">04. Interviewer Tone</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-px bg-outline-variant border border-outline-variant">
              {TONE_OPTIONS.map(opt => {
                const active = tone === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTone(opt.value)}
                    className={cn(
                      'flex items-start gap-3 p-3 transition-colors duration-150 text-left bg-surface min-h-[116px]',
                      active
                        ? 'bg-primary-container/10'
                        : 'hover:bg-surface-container',
                    )}
                  >
                    <span
                      className={cn(
                        'size-5 border shrink-0 flex items-center justify-center mt-0.5',
                        active ? 'bg-primary-container border-primary-container' : 'border-outline-variant',
                      )}
                    >
                      {active && <span className="size-2 bg-on-primary" />}
                    </span>
                    <span className="flex flex-col gap-1.5">
                      <span className={cn('label-mono uppercase', active ? 'text-primary-fixed-dim' : 'text-on-surface')}>
                        {opt.label}
                      </span>
                      <span className="text-body-md text-on-surface-variant normal-case">
                        {opt.description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 05. Proctoring & Integrity */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">05. Proctoring &amp; Integrity</h2>
            </div>
            <button
              type="button"
              onClick={() => setProctoringEnabled(enabled => !enabled)}
              className={cn(
                'w-full flex items-start gap-3 p-4 border transition-colors duration-150 text-left',
                proctoringEnabled
                  ? 'border-primary-container bg-primary-container/10'
                  : 'border-outline-variant bg-surface hover:bg-surface-container',
              )}
              aria-pressed={proctoringEnabled}
            >
              <span
                className={cn(
                  'size-5 border shrink-0 flex items-center justify-center mt-0.5',
                  proctoringEnabled
                    ? 'bg-primary-container border-primary-container'
                    : 'border-outline-variant',
                )}
              >
                {proctoringEnabled && <Check size={14} className="text-on-primary" />}
              </span>
              <span className="flex flex-col gap-1.5">
                <span className={cn('label-mono uppercase', proctoringEnabled ? 'text-primary-fixed-dim' : 'text-on-surface')}>
                  Enable Webcam Proctoring
                </span>
                <span className="text-body-md text-on-surface-variant normal-case">
                  Kandidly captures a webcam snapshot every 10 seconds while the interview is live.
                  Frames are analyzed for integrity signals — confirming the same candidate stays on
                  camera and flagging attention shifts, additional people, or an empty seat — and
                  appear on the interview review page alongside the transcript and score evidence.
                </span>
                <span className="text-body-md text-on-surface-variant normal-case">
                  Candidates are told about monitoring up front and must grant Kandidly camera
                  permission during the pre-interview check before the interview can begin.
                </span>
              </span>
            </button>
          </div>

          {/* 06. Access & Invitations */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">06. Access &amp; Invitations</h2>
            </div>
            <button
              type="button"
              onClick={() => setInviteOnly(enabled => !enabled)}
              className={cn(
                'w-full flex items-start gap-3 p-4 border transition-colors duration-150 text-left',
                inviteOnly
                  ? 'border-primary-container bg-primary-container/10'
                  : 'border-outline-variant bg-surface hover:bg-surface-container',
              )}
              aria-pressed={inviteOnly}
            >
              <span
                className={cn(
                  'size-5 border shrink-0 flex items-center justify-center mt-0.5',
                  inviteOnly
                    ? 'bg-primary-container border-primary-container'
                    : 'border-outline-variant',
                )}
              >
                {inviteOnly && <Check size={14} className="text-on-primary" />}
              </span>
              <span className="flex flex-col gap-1.5">
                <span className={cn('label-mono uppercase', inviteOnly ? 'text-primary-fixed-dim' : 'text-on-surface')}>
                  Invite-Only Interview
                </span>
                <span className="text-body-md text-on-surface-variant normal-case">
                  The interview link stays the same, but only candidates you invite below (by
                  email) can start the interview. Anyone else who opens the link is asked to sign
                  in with an invited email address. Turn this off to let anyone with the link
                  apply.
                </span>
                <span className="text-body-md text-on-surface-variant normal-case">
                  Invited candidates receive the interview link by email — immediately while the
                  requisition is live, or as soon as it is deployed.
                </span>
              </span>
            </button>
            {inviteOnly &&
              (existing ? (
                <InvitePanel requisitionId={existing.id} live={existing.status === 'open'} />
              ) : (
                <p className="mt-3 text-body-md text-on-surface-variant">
                  Deploy (or save) this requisition first — the invite list opens right here
                  afterwards.
                </p>
              ))}
          </div>

          {/* 07. Screening Form Builder */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">07. Screening Form Builder</h2>
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-[260px_minmax(0,1fr)] gap-5">
              {/* Toolbox */}
              <div className="w-full flex flex-col gap-3">
                <span className="label-mono text-on-surface-variant">Form Elements</span>
                <div className="grid grid-cols-2 xl:grid-cols-1 gap-2">
                  {FIELD_TYPES.map(ft => (
                    <button
                      key={ft.type}
                      type="button"
                      draggable
                      onDragStart={e => {
                        setDragging({ kind: 'new', type: ft.type });
                        e.dataTransfer.effectAllowed = 'copy';
                        e.dataTransfer.setData('text/plain', ft.type);
                      }}
                      onDragEnd={endDrag}
                      onClick={() => insertField(ft.type, fields.length)}
                      className="flex items-center gap-2 p-2.5 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim hover:bg-primary-container/5 transition-colors duration-150 label-mono justify-start cursor-grab active:cursor-grabbing"
                    >
                      <GripVertical size={14} className="text-on-surface-variant shrink-0 -ml-1" />
                      <ft.icon size={18} />
                      {ft.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Canvas — candidate-facing preview */}
              <div
                className={cn(
                  'w-full flex flex-col border min-h-[360px] transition-colors duration-150',
                  dragging ? 'border-primary-container' : 'border-outline-variant',
                )}
                style={{
                  backgroundColor: '#f8f9fa',
                  backgroundImage: 'linear-gradient(rgba(0, 0, 0, 0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 0, 0, 0.12) 1px, transparent 1px)',
                  backgroundSize: '20px 20px',
                }}
                onDragOver={e => {
                  if (!dragging) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = dragging.kind === 'new' ? 'copy' : 'move';
                  setDropIndex(fields.length);
                }}
                onDrop={handleCanvasDrop}
              >
                {/* Preview header — mimics the candidate screening page */}
                <div className="p-4 border-b border-outline-variant bg-surface">
                  <p className="label-mono text-on-surface-variant mb-1">Candidate Preview — Screening Form</p>
                  <p className="font-display text-headline-md text-on-surface">
                    {jobTitle.trim() || 'Untitled Role'}
                  </p>
                </div>

                <div className="flex-1 flex flex-col gap-3 p-4">
                  {fields.length === 0 && (
                    <div
                      className={cn(
                        'label-mono text-center border border-dashed p-8 my-auto transition-colors duration-150',
                        dragging 
                          ? 'border-primary-container text-primary-container' 
                          : 'border-outline-variant text-neutral-600',
                      )}
                    >
                      Drag a form element here to start building
                    </div>
                  )}

                  {fields.map((field, index) => {
                    const expanded = expandedFieldId === field.id;
                    const isDraggingThis = dragging?.kind === 'move' && dragging.id === field.id;
                    return (
                      <div key={field.id}>
                        {dragging && dropIndex === index && (
                          <div className="h-0.5 bg-primary-container mb-3" />
                        )}
                        <div
                          onDragOver={e => {
                            if (!dragging) return;
                            e.preventDefault();
                            e.stopPropagation();
                            e.dataTransfer.dropEffect = dragging.kind === 'new' ? 'copy' : 'move';
                            const rect = e.currentTarget.getBoundingClientRect();
                            const before = e.clientY < rect.top + rect.height / 2;
                            setDropIndex(before ? index : index + 1);
                          }}
                          className={cn(
                            'border bg-surface transition-colors duration-150',
                            isDraggingThis && 'opacity-40',
                            expanded ? 'border-primary-container' : 'border-outline-variant',
                          )}
                        >
                          {/* Builder toolbar */}
                          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-outline-variant bg-surface-container-lowest">
                            <button
                              type="button"
                              draggable
                              onDragStart={e => {
                                setDragging({ kind: 'move', id: field.id });
                                e.dataTransfer.effectAllowed = 'move';
                                e.dataTransfer.setData('text/plain', field.id);
                              }}
                              onDragEnd={endDrag}
                              className="text-on-surface-variant hover:text-on-surface p-1 -ml-1 cursor-grab active:cursor-grabbing"
                              title="Drag to reorder"
                            >
                              <GripVertical size={16} />
                            </button>
                            <span className="label-mono text-on-surface-variant">{FIELD_LABELS[field.type]}</span>
                            {field.required && (
                              <span className="label-mono text-primary-fixed-dim">· Required</span>
                            )}
                            <div className="ml-auto flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => setExpandedFieldId(expanded ? null : field.id)}
                                className={cn(
                                  'p-1.5 transition-colors duration-150',
                                  expanded
                                    ? 'text-primary-fixed-dim bg-primary-container/10'
                                    : 'text-on-surface-variant hover:text-on-surface',
                                )}
                                title="Configure element"
                              >
                                <Settings2 size={16} />
                              </button>
                              <button
                                type="button"
                                onClick={() => removeField(field.id)}
                                className="text-error hover:bg-error/10 p-1.5 transition-colors duration-150"
                                title="Remove element"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </div>

                          {/* Candidate-facing rendering */}
                          <div className="p-4">
                            <FieldPreview field={field} />
                          </div>

                          {/* Config panel */}
                          {expanded && (
                            <div className="border-t border-outline-variant p-4 bg-surface-container-lowest grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="flex flex-col gap-2">
                                <FieldLabel>Label</FieldLabel>
                                <input
                                  type="text"
                                  value={field.label}
                                  onChange={e => updateField(field.id, { label: e.target.value })}
                                  className={inputClasses(false)}
                                />
                              </div>
                              {PLACEHOLDER_TYPES.includes(field.type) && (
                                <div className="flex flex-col gap-2">
                                  <FieldLabel>
                                    {field.type === 'file' ? 'Helper Text' : 'Placeholder'}
                                  </FieldLabel>
                                  <input
                                    type="text"
                                    value={field.placeholder}
                                    onChange={e => updateField(field.id, { placeholder: e.target.value })}
                                    className={inputClasses(false)}
                                  />
                                </div>
                              )}
                              {CHOICE_TYPES.includes(field.type) && (
                                <div className="flex flex-col gap-2 sm:col-span-2">
                                  <FieldLabel>Options (one per line)</FieldLabel>
                                  <textarea
                                    value={field.options.join('\n')}
                                    onChange={e => updateField(field.id, { options: e.target.value.split('\n') })}
                                    className={cn(inputClasses(false), 'h-24 resize-none')}
                                  />
                                </div>
                              )}
                              <label className="flex items-center gap-3 cursor-pointer sm:col-span-2">
                                <input
                                  type="checkbox"
                                  checked={field.required}
                                  onChange={e => updateField(field.id, { required: e.target.checked })}
                                  className="size-4 accent-current"
                                />
                                <span className="label-mono text-on-surface-variant">
                                  Required — candidates must answer before submitting
                                </span>
                              </label>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  {dragging && dropIndex === fields.length && fields.length > 0 && (
                    <div className="h-0.5 bg-primary-container" />
                  )}
                </div>

                {/* Inert submit — completes the candidate preview */}
                {fields.length > 0 && (
                  <div className="p-4 border-t border-outline-variant pointer-events-none select-none">
                    <span className="inline-block label-mono text-on-primary bg-primary-container uppercase px-6 py-2.5">
                      Submit & Continue to Interview
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 07. Assessment Rubrics */}
          <div className="p-5 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-headline-md text-on-surface">08. Assessment Rubrics</h2>
            </div>
            <div className="flex flex-col gap-4">
              {criteria.map(c => (
                <div key={c.id} className="border border-outline-variant p-4 flex flex-col gap-3 bg-surface-container-lowest">
                  {/* Top Row: Name on the left, Weightage & Delete on the right */}
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <input
                      type="text"
                      value={c.name}
                      onChange={e => updateCriterion(c.id, { name: e.target.value })}
                      placeholder="e.g. Technical Proficiency"
                      className={cn(
                        "bg-transparent p-0 pb-1 flex-1 font-display text-body-lg text-on-surface focus:outline-none placeholder:text-on-surface-variant/40 border-b",
                        attempted && !c.name.trim()
                          ? "border-error focus:border-error"
                          : "border-transparent focus:border-primary"
                      )}
                    />
                    <div className="flex items-center gap-4 shrink-0">
                      <span className="label-mono text-primary-fixed-dim uppercase px-2 py-1 border border-primary-container bg-primary-container/10">
                        Required
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="label-mono text-on-surface-variant text-body-sm">Weightage:</span>
                        <div className="relative flex items-center">
                          <input
                            type="number"
                            value={c.weight || ''}
                            onChange={e => updateCriterion(c.id, { weight: Number(e.target.value) || 0 })}
                            placeholder="0"
                            className="bg-surface border border-outline-variant focus:border-primary rounded-md pl-3 pr-8 py-1.5 w-24 text-right text-body-md text-on-surface focus:outline-none transition-colors duration-150"
                          />
                          <span className="absolute right-3 text-on-surface-variant text-body-md pointer-events-none select-none">%</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeCriterion(c.id)}
                        className="text-error hover:bg-error/10 p-2 rounded transition-colors duration-150 flex items-center justify-center"
                        title="Remove criteria"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Bottom Row: Description (full-width textarea) */}
                  <div className="w-full">
                    <textarea
                      value={c.description}
                      onChange={e => updateCriterion(c.id, { description: e.target.value })}
                      placeholder="Describe what and how to judge for this criterion..."
                      className={cn(
                        'bg-surface-container-lowest border rounded-lg p-3 w-full h-16 text-body-md text-on-surface focus:outline-none transition-colors duration-150 resize-none placeholder:text-on-surface-variant/40',
                        attempted && !c.description.trim()
                          ? 'border-error focus:border-error focus:ring-1 focus:ring-error'
                          : 'border-outline-variant focus:border-primary',
                      )}
                    />
                  </div>
                </div>
              ))}

              {/* Summary row / Status bar */}
              <div className="p-4 bg-surface-variant/10 border border-outline-variant flex justify-between items-center">
                <span className="label-mono text-on-surface-variant">Total Rubric Weightage</span>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      'text-headline-md font-bold',
                      totalWeight === 100 ? 'text-primary-fixed-dim' : 'text-error',
                    )}
                  >
                    {totalWeight}%
                  </span>
                  {totalWeight !== 100 && (
                    <span className="label-mono text-error text-body-sm">(Must total 100%)</span>
                  )}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={addCriterion}
              className="mt-3 flex items-center gap-2 px-5 py-2 border border-primary-container text-primary-fixed-dim label-mono hover:bg-primary-container/5 transition-colors duration-150"
            >
              <Plus size={18} />
              Add Criteria
            </button>
          </div>

          {/* Footer */}
          <footer className="mt-auto py-4 px-5 flex flex-col md:flex-row justify-between items-center gap-3 border-t border-outline-variant bg-surface-container-lowest">
            <p className="font-display text-headline-md font-bold text-primary-fixed-dim">KANDIDLY AI</p>
            <p className="label-mono text-on-surface-variant">© 2026 Kandidly AI. All rights reserved.</p>
          </footer>
        </div>
      </div>

      {/* Save action bar */}
      <div className="h-14 border-t border-outline-variant bg-surface-container-lowest flex justify-between items-center px-8 sticky bottom-0 z-30 shrink-0">
        <div className="flex items-center gap-2">
          {atRequisitionLimit ? (
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-error" />
              <span className="label-mono text-error">
                Free plan limit reached ({usage!.requisitions_used}/{usage!.requisitions_limit}{' '}
                requisitions) — please upgrade to deploy more interviews
              </span>
            </div>
          ) : errors.length > 0 ? (
            <div className="relative group flex items-center gap-2 cursor-help">
              <AlertTriangle size={16} className="text-error" />
              <span className="label-mono text-error border-b border-dashed border-error pb-0.5">
                {errors.length} {errors.length === 1 ? 'Error' : 'Errors'} Needs Resolution
              </span>
              
              {/* Tooltip */}
              <div className="absolute bottom-full left-0 mb-3 hidden group-hover:block bg-surface-container-high border border-outline-variant text-on-surface text-sm rounded-lg p-3 shadow-lg z-50 w-80 pointer-events-none">
                <p className="font-semibold text-body-md mb-2 text-error flex items-center gap-1.5">
                  <AlertTriangle size={14} />
                  Necessary steps to publish:
                </p>
                <ul className="list-disc pl-4 space-y-1.5 text-on-surface-variant text-sm">
                  {errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
                {/* Arrow */}
                <div className="absolute top-full left-6 w-3 h-3 bg-surface-container-high border-r border-b border-outline-variant rotate-45 -mt-1.5" />
              </div>
            </div>
          ) : (
            <span className="label-mono text-primary-fixed-dim">All checks passed</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            disabled={!isEditing || saving || deleting}
            title={isEditing ? 'Delete this requisition' : 'Nothing to delete yet — the requisition has not been saved'}
            className={cn(
              'label-mono uppercase border px-5 py-2 transition-colors duration-150 flex items-center gap-2',
              !isEditing || saving || deleting
                ? 'text-error/50 border-error/30 opacity-50 cursor-not-allowed'
                : 'text-error border-error hover:bg-error/10',
            )}
          >
            <Trash2 size={14} />
            Delete Requisition
          </button>
          <button
            type="button"
            onClick={handleSaveOffline}
            disabled={saving || !jobTitle.trim() || !domain.trim()}
            className={cn(
              "label-mono text-on-surface uppercase border border-outline-variant px-5 py-2 hover:bg-surface-variant transition-colors duration-150 flex items-center gap-2",
              saving || !jobTitle.trim() || !domain.trim() ? "opacity-50 cursor-not-allowed" : "hover:text-error hover:border-error"
            )}
          >
            {saving ? (
              <>
                Saving...
                <Spinner size={14} className="text-on-surface" />
              </>
            ) : (
              errors.length > 0 ? 'Save as Draft' : 'Save as Offline'
            )}
          </button>
          <button
            type="button"
            onClick={handleDeploy}
            disabled={saving || errors.length > 0}
            className={cn(
              'label-mono text-white font-bold bg-primary-container uppercase border border-primary-container px-5 py-2 transition-colors duration-150 flex items-center gap-2',
              errors.length > 0 || saving ? 'opacity-50 cursor-not-allowed' : 'hover:bg-transparent hover:text-primary-fixed-dim',
            )}
          >
            Deploy Interview
            <Rocket size={16} />
          </button>
        </div>
      </div>

      {confirmingDelete && existing && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          role="alertdialog"
          aria-modal="true"
          aria-label="Delete requisition"
          onClick={() => !deleting && setConfirmingDelete(false)}
        >
          <div className="absolute inset-0 bg-black/70 backdrop-blur-md" />
          <div
            className="relative w-full max-w-md border border-error bg-surface-container-lowest shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-6 space-y-4">
              <div className="flex items-start gap-3">
                <div className="size-10 shrink-0 flex items-center justify-center border border-error/40 bg-error/10 text-error">
                  <AlertTriangle size={18} />
                </div>
                <div className="min-w-0">
                  <h2 className="font-display font-bold text-on-surface leading-tight">
                    Delete this requisition?
                  </h2>
                  <p className="label-mono text-error mt-1">This cannot be undone</p>
                </div>
              </div>
              <div className="border border-outline-variant bg-surface px-4 py-3">
                <p className="text-sm font-medium text-on-surface truncate">{existing.title}</p>
                <p className="label-mono text-on-surface-variant mt-0.5">{existing.code}</p>
              </div>
              <p className="text-sm text-on-surface-variant leading-relaxed">
                Deleting <span className="text-on-surface">{existing.code}</span> removes it from
                your console permanently and takes its interview link offline. Interviews already
                taken against it are kept and stay visible in the Interviews ledger — but you will
                no longer be able to view or edit this requisition.
              </p>
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-outline-variant">
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
                className="label-mono uppercase text-on-surface border border-outline-variant px-5 py-2 hover:bg-surface-container transition-colors duration-150 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={deleting}
                className="label-mono uppercase font-bold text-on-error-container bg-error-container border border-error-container px-5 py-2 hover:bg-transparent hover:text-error hover:border-error transition-colors duration-150 flex items-center gap-2 disabled:opacity-60"
              >
                {deleting ? (
                  <>
                    Deleting…
                    <Spinner size={14} className="text-on-error-container" />
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    Delete Requisition
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {deployState !== 'idle' && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-[#0c0e17]/95 backdrop-blur-md animate-fade-in select-none">
          <style dangerouslySetInnerHTML={{ __html: `
            @keyframes fadeIn {
              from { opacity: 0; }
              to { opacity: 1; }
            }
            @keyframes scaleUp {
              from { transform: scale(0.95); opacity: 0; }
              to { transform: scale(1); opacity: 1; }
            }
            @keyframes bounceShort {
              0%, 100% { transform: translateY(0); }
              50% { transform: translateY(-4px); }
            }
            @keyframes countdown {
              from { width: 100%; }
              to { width: 0%; }
            }
            @keyframes spinClockwise {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
            @keyframes spinCounterClockwise {
              from { transform: rotate(360deg); }
              to { transform: rotate(0deg); }
            }
            @keyframes pulseGlow {
              0%, 100% { transform: scale(0.85); opacity: 0.5; }
              50% { transform: scale(1.15); opacity: 1; }
            }
            .animate-fade-in {
              animation: fadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
            }
            .animate-scale-up {
              animation: scaleUp 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
            }
            .animate-bounce-short {
              animation: bounceShort 2s ease-in-out infinite;
            }
            .animate-countdown-progress {
              animation: countdown 6s linear forwards;
            }
            .animate-spin-slow {
              animation: spinClockwise 8s linear infinite;
            }
            .animate-spin-reverse {
              animation: spinCounterClockwise 3s linear infinite;
            }
            .animate-pulse-glow {
              animation: pulseGlow 1.5s ease-in-out infinite;
            }
          `}} />

          {/* Top-right close button (Only available on success) */}
          {deployState === 'success' && (
            <button
              onClick={handleCloseSplash}
              className="absolute top-6 right-6 text-on-surface-variant hover:text-on-surface hover:rotate-90 transition-all duration-300 p-2 border border-outline-variant hover:border-primary-container bg-surface-container/30 rounded-full animate-fade-in"
              title="Close and continue"
            >
              <X size={20} />
            </button>
          )}

          {/* Background Glow */}
          <div className="absolute w-[450px] h-[450px] rounded-full bg-primary-container/20 blur-[120px] pointer-events-none" />

          {/* Processing State */}
          {deployState === 'processing' && (
            <div className="relative text-center max-w-xl px-6 flex flex-col items-center animate-scale-up">
              {/* Custom Blueprint Loader */}
              <div className="relative mb-8 w-24 h-24 flex items-center justify-center">
                {/* Outer dashed ring */}
                <div className="absolute inset-0 rounded-full border border-dashed border-outline-variant/60 animate-spin-slow" />
                {/* Middle ring with gaps */}
                <div className="absolute inset-3 rounded-full border border-double border-primary-container border-t-transparent border-b-transparent animate-spin-reverse" />
                {/* Inner target circle */}
                <div className="absolute inset-6 rounded-full border border-primary-fixed-dim/40 flex items-center justify-center">
                  {/* Central pulsing core */}
                  <div className="w-3 h-3 rounded-full bg-primary-container animate-pulse-glow shadow-[0_0_12px_rgba(46,91,255,0.6)]" />
                </div>
              </div>

              {/* Title */}
              <h1 className="font-display text-4xl font-bold tracking-tight mb-4 text-on-surface">
                Deploying Interview
              </h1>

              {/* Subtitle */}
              <p className="text-on-surface-variant text-body-md mb-8 max-w-sm">
                Configuring screening routes and deploying the interactive assessment workspace...
              </p>
            </div>
          )}

          {/* Success State */}
          {deployState === 'success' && (
            <div className="relative text-center max-w-xl px-6 flex flex-col items-center animate-scale-up">
              {/* Live Indicator Chip */}
              <div className="mb-6 px-3 py-1 label-mono text-xs flex items-center gap-2 select-none border border-[var(--emerald-chip-text)]/20 bg-[var(--emerald-chip-bg)] text-[var(--emerald-chip-text)] rounded-full">
                <span className="size-2 bg-[var(--emerald-chip-text)] blink rounded-full" />
                DEPLOYMENT LIVE
              </div>

              {/* Glowing Success Ring and Checkmark */}
              <div className="relative mb-8 w-24 h-24 flex items-center justify-center">
                {/* Outer pulsing ring */}
                <div className="absolute inset-0 rounded-full border-4 border-primary-container/30 animate-ping duration-1000" />
                {/* Middle glowing border */}
                <div className="absolute inset-2 rounded-full border border-primary-container/60 shadow-[0_0_20px_rgba(46,91,255,0.4)]" />
                {/* Inner circle with Check */}
                <div className="absolute inset-3 rounded-full bg-primary-container flex items-center justify-center animate-bounce-short">
                  <Check size={36} className="text-on-primary stroke-[3px]" />
                </div>
              </div>

              {/* Title with Gradient */}
              <h1 className="font-display text-4xl font-bold tracking-tight mb-4 text-on-surface">
                Interview Deployed
              </h1>

              {/* Requisition Name */}
              <p className="text-xl font-medium text-primary-fixed-dim mb-4 max-w-md break-words font-sans">
                {jobTitle}
              </p>

              {/* Explanation */}
              <p className="text-on-surface-variant text-body-md mb-8 max-w-sm">
                The requisition is live. Candidates can now access the interview link and begin their assessments.
              </p>

              {/* Auto-closing Progress Bar */}
              <div className="w-64 h-1 bg-surface-container-highest overflow-hidden relative border border-outline-variant/30">
                <div className="absolute top-0 bottom-0 left-0 bg-primary-container animate-countdown-progress" />
              </div>
              <p className="text-xs text-on-surface-variant/60 mt-2 font-mono">
                Redirecting to all requisitions page...
              </p>
            </div>
          )}
        </div>
      )}
    </ConsoleLayout>
  );
}
