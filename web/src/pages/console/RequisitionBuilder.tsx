/**
 * /console/requisitions/new — Requisition Builder.
 * Configures an AI-conducted screening interview: core details (with
 * autocomplete against known titles/domains), role context + sample questions,
 * skill chips, interviewer tone, a drag-and-drop screening form builder that
 * renders a candidate-facing preview, and weighted assessment rubrics.
 */

import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Calendar,
  CheckSquare,
  CircleDot,
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
import { useToast } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';

/* -------------------------------------------------------------------------- */
/*  Types & constants                                                         */
/* -------------------------------------------------------------------------- */

type Tone = 'conversational' | 'friendly' | 'technical' | 'structured' | 'bar_raiser';

const TONE_OPTIONS: { value: Tone; label: string; description: string }[] = [
  {
    value: 'conversational',
    label: 'Conversational',
    description:
      'Relaxed and natural. The interviewer keeps the exchange informal and lets topics flow like a normal chat — a good default for early screening rounds.',
  },
  {
    value: 'friendly',
    label: 'Friendly & Encouraging',
    description:
      'Warm and reassuring. Offers gentle prompts and puts nervous candidates at ease — well suited to junior roles and high-volume hiring.',
  },
  {
    value: 'technical',
    label: 'Technical / Strict',
    description:
      'Focused and rigorous. Drills into implementation detail, asks for specifics, and follows up on vague answers — best for senior technical screens.',
  },
  {
    value: 'structured',
    label: 'Formal & Structured',
    description:
      'Professional and consistent. Every candidate receives the same structured question flow, making results easy to compare — ideal when fairness and auditability matter most.',
  },
  {
    value: 'bar_raiser',
    label: 'Challenging / Bar-Raiser',
    description:
      'Deliberately probing. Pushes back on claims and stress-tests reasoning under pressure — reserve for senior and leadership positions.',
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

// Mock lookup lists standing in for DB-backed autocomplete (to be replaced by
// API calls). Values a user "creates" are appended for the session.
const DB_JOB_TITLES = [
  'Senior AI Engineer', 'Product Designer', 'Growth Manager', 'Frontend Engineer',
  'Data Scientist', 'DevOps Lead', 'Backend Engineer', 'Product Manager',
  'Machine Learning Engineer', 'Engineering Manager', 'QA Engineer', 'Technical Writer',
];

const DB_DOMAINS = [
  'Machine Learning', 'Product', 'Marketing', 'Engineering', 'Data Science',
  'Infrastructure', 'Design', 'Sales', 'Customer Success', 'Finance', 'People & Talent',
];

const DB_SKILLS = [
  'React', 'TypeScript', 'GraphQL', 'Node.js', 'Python', 'PyTorch', 'RAG',
  'Vector DBs', 'SQL', 'PostgreSQL', 'Kubernetes', 'Terraform', 'AWS', 'CI/CD',
  'Figma', 'Design Systems', 'Prototyping', 'GA4', 'Lifecycle Automation',
  'API Design', 'Forecasting', 'ML Ops', 'Analytics', 'Agile Delivery',
  'Accessibility', 'Go', 'Rust', 'Java',
];

let idCounter = 0;
const nextId = () => `el-${++idCounter}`;

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
      } else if (input.trim()) {
        const canonical = suggestions.find(s => s.toLowerCase() === query);
        if (canonical) {
          addChip(canonical);
        } else {
          onCreate(input.trim());
          addChip(input.trim());
        }
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
          onBlur={() => { setOpen(false); onBlur?.(); }}
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
  const navigate = useNavigate();
  const { toast } = useToast();

  const [jobTitle, setJobTitle]   = useState('');
  const [domain, setDomain]       = useState('');
  const [objective, setObjective] = useState('');
  const [skills, setSkills]       = useState<string[]>([]);
  const [tone, setTone]           = useState<Tone>('technical');
  const [touched, setTouched]     = useState<Record<string, boolean>>({});
  const [attempted, setAttempted] = useState(false);

  // Session-local stand-ins for DB lookups; "created" values persist here.
  const [jobTitleDb, setJobTitleDb] = useState<string[]>(DB_JOB_TITLES);
  const [domainDb, setDomainDb]     = useState<string[]>(DB_DOMAINS);
  const [skillDb, setSkillDb]       = useState<string[]>(DB_SKILLS);

  const [sampleQuestions, setSampleQuestions] = useState<SampleQuestion[]>([]);

  const [fields, setFields] = useState<ScreeningField[]>([]);
  const [expandedFieldId, setExpandedFieldId] = useState<string | null>(null);
  const [dragging, setDragging] = useState<DragPayload | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  const [criteria, setCriteria] = useState<RubricCriterion[]>([
    { id: nextId(), name: 'Technical Skill', description: '', weight: 60 },
    { id: nextId(), name: 'Communication',   description: '', weight: 40 },
  ]);

  const totalWeight = useMemo(() => criteria.reduce((sum, c) => sum + (c.weight || 0), 0), [criteria]);

  const errors = useMemo(() => {
    const list: string[] = [];
    if (!jobTitle.trim())    list.push('Job title is required.');
    if (!domain.trim())      list.push('Domain is required.');
    if (skills.length === 0) list.push('Add at least one must-have skill.');
    if (totalWeight !== 100) list.push('Rubric weightage must total 100%.');
    return list;
  }, [jobTitle, domain, skills, totalWeight]);

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

  const handleDeploy = () => {
    if (errors.length > 0) {
      setAttempted(true);
      toast('Resolve the errors below before deploying.', 'error');
      return;
    }
    toast(`"${jobTitle}" deployed. Candidates can now be invited.`, 'success');
    navigate('/console/requisitions');
  };

  const handleSaveOffline = () => {
    toast(`"${jobTitle || 'Untitled requisition'}" saved as an offline draft.`, 'info');
    navigate('/console/requisitions');
  };

  const skillsInvalid = showError('skills') && skills.length === 0;

  return (
    <ConsoleLayout>
      {/* Header */}
      <header className="h-16 border-b border-outline-variant bg-surface flex items-center px-8 sticky top-0 z-30">
        <span className="label-mono text-on-surface-variant">Requisition Builder</span>
      </header>

      {/* Content */}
      <div className="flex-1">
        <div className="max-w-[1000px] w-full mx-auto flex flex-col border-x border-outline-variant">
          {/* Title block */}
          <div className="p-8 border-b border-outline-variant bg-surface-container-lowest">
            <h1 className="font-display text-headline-lg text-on-surface mb-2">New Requisition</h1>
            <p className="text-body-md text-on-surface-variant max-w-[70ch]">
              A requisition is the blueprint for an AI-conducted screening interview. Describe the
              role you're hiring for, the skills that matter, and how the interview should feel —
              Kandidly turns it into a live, structured conversation with each candidate. Once
              deployed, you'll get a shareable link to send to potential candidates, and every
              completed interview lands back here as a scored, evidence-backed report ready for
              your review.
            </p>
          </div>

          {/* 01. Core Details */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-headline-md text-on-surface">01. Core Details</h2>
              <span className="label-mono text-primary-fixed-dim uppercase px-2 py-1 border border-primary-container bg-primary-container/10">
                Required
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
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
            </div>
          </div>

          {/* 02. Role Context */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-headline-md text-on-surface">02. Role Context</h2>
            </div>
            <p className="text-body-md text-on-surface-variant max-w-[70ch] mb-6">
              Help the interviewer understand who you're looking for. Describe the kind of
              candidate who would thrive in this role — their experience, strengths, and working
              style — along with what the role needs to achieve. The more context you give here,
              the more precisely Kandidly can steer its questions. You can also add sample
              questions below as a reference for the topics and depth you'd like covered.
            </p>
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-2">
                <FieldLabel>Ideal Candidate & Role Objective</FieldLabel>
                <textarea
                  value={objective}
                  onChange={e => setObjective(e.target.value)}
                  placeholder="e.g. We need a hands-on engineer who has scaled a consumer product past a million users, communicates clearly with non-technical stakeholders, and can own our checkout flow end-to-end within the first quarter..."
                  className={cn(inputClasses(false), 'h-32 resize-none')}
                />
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <FieldLabel>Sample Questions (Optional)</FieldLabel>
                  <span className="text-body-md text-on-surface-variant">
                    Kandidly uses these as reference points — it may adapt the wording, but will
                    make sure the same ground gets covered.
                  </span>
                </div>
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
              'p-8 border-b border-outline-variant',
              skillsInvalid && 'bg-surface/50 border-l-[4px] border-l-error',
            )}
          >
            <div className="flex items-center justify-between mb-6">
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
                Pick from existing skills, or type a new one and press Enter to create it.
              </span>
              {skillsInvalid && (
                <span className="label-mono text-error normal-case tracking-normal">
                  Add at least one must-have skill.
                </span>
              )}
            </div>
          </div>

          {/* 04. Interviewer Tone */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-headline-md text-on-surface">04. Interviewer Tone</h2>
            </div>
            <p className="text-body-md text-on-surface-variant max-w-[70ch] mb-6">
              Choose how Kandidly should carry itself during the interview. The tone shapes
              phrasing, pacing, and how hard the interviewer pushes on follow-ups.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {TONE_OPTIONS.map(opt => {
                const active = tone === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTone(opt.value)}
                    className={cn(
                      'flex items-start gap-3 p-4 border transition-colors duration-150 text-left',
                      active
                        ? 'border-primary-container bg-primary-container/10'
                        : 'border-outline-variant hover:bg-surface-container',
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

          {/* 05. Screening Form Builder */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-headline-md text-on-surface">05. Screening Form Builder</h2>
            </div>
            <p className="text-body-md text-on-surface-variant max-w-[70ch] mb-6">
              Build the short form candidates complete before their interview begins. Drag
              elements from the palette into the form — the preview on the right shows the form
              exactly as candidates will see it. Use the <Settings2 size={14} className="inline -mt-0.5" /> icon
              on any element to configure its label, placeholder, and whether it's required.
            </p>
            <div className="flex flex-col lg:flex-row gap-8">
              {/* Toolbox */}
              <div className="w-full lg:w-1/3 flex flex-col gap-4">
                <span className="label-mono text-on-surface-variant">Form Elements — drag onto the form, or click to append</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">
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
                      className="flex items-center gap-3 p-3 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim hover:bg-primary-container/5 transition-colors duration-150 label-mono justify-start cursor-grab active:cursor-grabbing"
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
                  'w-full lg:w-2/3 flex flex-col border bg-surface-container-lowest min-h-[400px] transition-colors duration-150',
                  dragging ? 'border-primary-container' : 'border-outline-variant',
                )}
                onDragOver={e => {
                  if (!dragging) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = dragging.kind === 'new' ? 'copy' : 'move';
                  setDropIndex(fields.length);
                }}
                onDrop={handleCanvasDrop}
              >
                {/* Preview header — mimics the candidate screening page */}
                <div className="p-6 border-b border-outline-variant bg-surface">
                  <p className="label-mono text-on-surface-variant mb-2">Candidate Preview — Screening Form</p>
                  <p className="font-display text-headline-md text-on-surface">
                    {jobTitle.trim() || 'Untitled Role'}
                  </p>
                  <p className="text-body-md text-on-surface-variant mt-1">
                    Please answer a few quick questions before your interview begins.
                  </p>
                </div>

                <div className="flex-1 flex flex-col gap-3 p-6">
                  {fields.length === 0 && (
                    <div
                      className={cn(
                        'label-mono text-on-surface-variant text-center border border-dashed p-10 my-auto transition-colors duration-150',
                        dragging ? 'border-primary-container text-primary-fixed-dim' : 'border-outline-variant',
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
                  <div className="p-6 border-t border-outline-variant pointer-events-none select-none">
                    <span className="inline-block label-mono text-on-primary bg-primary-container uppercase px-6 py-2.5">
                      Submit & Continue to Interview
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 06. Assessment Rubrics */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-headline-md text-on-surface">06. Assessment Rubrics</h2>
            </div>
            <div className="flex flex-col border border-outline-variant bg-surface-container-lowest">
              {/* Table header */}
              <div className="grid grid-cols-12 border-b border-outline-variant bg-surface-variant/30">
                <div className="col-span-7 p-3 border-r border-outline-variant label-mono text-on-surface-variant">Criterion</div>
                <div className="col-span-3 p-3 border-r border-outline-variant label-mono text-on-surface-variant">Weightage (%)</div>
                <div className="col-span-2 p-3 label-mono text-on-surface-variant text-center">Action</div>
              </div>

              {criteria.map(c => (
                <div key={c.id} className="grid grid-cols-12 border-b border-outline-variant">
                  <div className="col-span-7 border-r border-outline-variant p-3 flex flex-col gap-2">
                    <input
                      type="text"
                      value={c.name}
                      onChange={e => updateCriterion(c.id, { name: e.target.value })}
                      placeholder="e.g. Technical Proficiency"
                      className="bg-transparent border-none p-0 w-full text-body-md text-on-surface focus:outline-none focus:ring-0"
                    />
                    <textarea
                      value={c.description}
                      onChange={e => updateCriterion(c.id, { description: e.target.value })}
                      placeholder="Describe what and how to judge for this criterion..."
                      className="bg-transparent border border-outline-variant p-2 w-full h-20 text-body-md text-on-surface focus:outline-none focus:ring-0 resize-none"
                    />
                  </div>
                  <div className="col-span-3 border-r border-outline-variant flex items-start">
                    <input
                      type="number"
                      value={c.weight}
                      onChange={e => updateCriterion(c.id, { weight: Number(e.target.value) || 0 })}
                      placeholder="0"
                      className="bg-transparent border-none p-3 w-full text-body-md text-on-surface focus:outline-none focus:ring-0"
                    />
                  </div>
                  <div className="col-span-2 flex items-start justify-center">
                    <button
                      type="button"
                      onClick={() => removeCriterion(c.id)}
                      className="text-error hover:bg-error/10 w-full py-3 transition-colors duration-150 flex items-center justify-center"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}

              {/* Summary row */}
              <div className="grid grid-cols-12 bg-surface-variant/10">
                <div className="col-span-7 p-3 border-r border-outline-variant label-mono text-right">Total Weightage</div>
                <div
                  className={cn(
                    'col-span-3 p-3 border-r border-outline-variant label-mono font-bold',
                    totalWeight === 100 ? 'text-primary-fixed-dim' : 'text-error',
                  )}
                >
                  {totalWeight}%
                </div>
                <div className="col-span-2 bg-surface-container-lowest" />
              </div>
            </div>
            <button
              type="button"
              onClick={addCriterion}
              className="mt-4 flex items-center gap-2 px-6 py-3 border border-primary-container text-primary-fixed-dim label-mono hover:bg-primary-container/5 transition-colors duration-150"
            >
              <Plus size={18} />
              Add Criteria
            </button>
          </div>

          {/* Footer */}
          <footer className="mt-auto py-8 px-8 flex flex-col md:flex-row justify-between items-center gap-4 border-t border-outline-variant bg-surface-container-lowest">
            <p className="font-display text-headline-md font-bold text-primary-fixed-dim">KANDIDLY AI</p>
            <p className="label-mono text-on-surface-variant">© 2026 Kandidly AI. All rights reserved.</p>
          </footer>
        </div>
      </div>

      {/* Save action bar */}
      <div className="h-16 border-t border-outline-variant bg-surface-container-lowest flex justify-between items-center px-8 sticky bottom-0 z-30 shrink-0">
        <div className="flex items-center gap-2">
          {errors.length > 0 ? (
            <>
              <AlertTriangle size={16} className="text-error" />
              <span className="label-mono text-error">
                {errors.length} {errors.length === 1 ? 'Error' : 'Errors'} Needs Resolution
              </span>
            </>
          ) : (
            <span className="label-mono text-primary-fixed-dim">All checks passed</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleSaveOffline}
            className="label-mono text-on-surface uppercase border border-outline-variant px-6 py-2 hover:bg-surface-variant hover:text-error hover:border-error transition-colors duration-150"
          >
            Save as Offline
          </button>
          <button
            type="button"
            onClick={handleDeploy}
            className={cn(
              'label-mono text-on-primary bg-primary-container uppercase border border-primary-container px-6 py-2 transition-colors duration-150 flex items-center gap-2',
              errors.length > 0 ? 'opacity-50 cursor-not-allowed' : 'hover:bg-transparent hover:text-primary-fixed-dim',
            )}
          >
            Deploy Interview
            <Rocket size={16} />
          </button>
        </div>
      </div>
    </ConsoleLayout>
  );
}
