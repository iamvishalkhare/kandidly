/**
 * /console/requisitions/new — Requisition Builder.
 * Configures AI interview parameters: core details, role context, must-have
 * skills, interviewer tone, a screening form, and weighted assessment rubrics.
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Calendar,
  CheckSquare,
  CircleDot,
  Globe,
  ListChecks,
  Plus,
  Rocket,
  SlidersHorizontal,
  Trash2,
  Type,
  Upload,
} from 'lucide-react';
import { cn } from '../../lib/utils';
import { useToast } from '../../components/ui';
import ConsoleLayout from './ConsoleLayout';

/* -------------------------------------------------------------------------- */
/*  Types & constants                                                         */
/* -------------------------------------------------------------------------- */

type Tone = 'conversational' | 'technical';

type FieldType =
  | 'text' | 'textarea' | 'multiple_choice' | 'multi_select'
  | 'range' | 'date' | 'file' | 'social';

interface ScreeningField {
  id: string;
  type: FieldType;
  label: string;
}

interface RubricCriterion {
  id: string;
  name: string;
  description: string;
  weight: number;
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

let idCounter = 0;
const nextId = () => `el-${++idCounter}`;

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
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

export default function RequisitionBuilder() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [jobTitle, setJobTitle]     = useState('');
  const [department, setDepartment] = useState('');
  const [objective, setObjective]   = useState('');
  const [skills, setSkills]         = useState('');
  const [tone, setTone]             = useState<Tone>('technical');
  const [touched, setTouched]       = useState<Record<string, boolean>>({});
  const [attempted, setAttempted]   = useState(false);

  const [fields, setFields] = useState<ScreeningField[]>([]);
  const [criteria, setCriteria] = useState<RubricCriterion[]>([
    { id: nextId(), name: 'Technical Skill', description: '', weight: 60 },
    { id: nextId(), name: 'Communication',   description: '', weight: 40 },
  ]);

  const totalWeight = useMemo(() => criteria.reduce((sum, c) => sum + (c.weight || 0), 0), [criteria]);

  const errors = useMemo(() => {
    const list: string[] = [];
    if (!jobTitle.trim())   list.push('Job title is required.');
    if (!department.trim()) list.push('Department / team is required.');
    if (!skills.trim())     list.push('Must-have skills cannot be empty for engineering roles.');
    if (totalWeight !== 100) list.push('Rubric weightage must total 100%.');
    return list;
  }, [jobTitle, department, skills, totalWeight]);

  const showError = (field: string) => (touched[field] || attempted);
  const markTouched = (field: string) => setTouched(t => ({ ...t, [field]: true }));

  const addField = (type: FieldType) => {
    setFields(f => [...f, { id: nextId(), type, label: `New ${FIELD_LABELS[type]}` }]);
  };
  const removeField = (id: string) => setFields(f => f.filter(x => x.id !== id));
  const updateFieldLabel = (id: string, label: string) =>
    setFields(f => f.map(x => (x.id === id ? { ...x, label } : x)));

  const addCriterion = () =>
    setCriteria(c => [...c, { id: nextId(), name: '', description: '', weight: 0 }]);
  const removeCriterion = (id: string) => setCriteria(c => c.filter(x => x.id !== id));
  const updateCriterion = (id: string, patch: Partial<RubricCriterion>) =>
    setCriteria(c => c.map(x => (x.id === id ? { ...x, ...patch } : x)));

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

  const skillsInvalid = showError('skills') && !skills.trim();

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
            <p className="text-body-md text-on-surface-variant">
              Configure AI parameters for candidate evaluation.
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
                <input
                  type="text"
                  value={jobTitle}
                  onChange={e => setJobTitle(e.target.value)}
                  onBlur={() => markTouched('jobTitle')}
                  placeholder="e.g. Senior Frontend Engineer"
                  className={inputClasses(showError('jobTitle') && !jobTitle.trim())}
                />
                {showError('jobTitle') && !jobTitle.trim() && (
                  <span className="label-mono text-error normal-case tracking-normal">Job title is required.</span>
                )}
              </div>
              <div className="flex flex-col gap-2">
                <FieldLabel required>Department / Team</FieldLabel>
                <input
                  type="text"
                  value={department}
                  onChange={e => setDepartment(e.target.value)}
                  onBlur={() => markTouched('department')}
                  placeholder="e.g. Platform Engineering"
                  className={inputClasses(showError('department') && !department.trim())}
                />
                {showError('department') && !department.trim() && (
                  <span className="label-mono text-error normal-case tracking-normal">Department is required.</span>
                )}
              </div>
            </div>
          </div>

          {/* 02. Role Context */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-headline-md text-on-surface">02. Role Context</h2>
            </div>
            <div className="flex flex-col gap-2">
              <FieldLabel>Primary Objective</FieldLabel>
              <textarea
                value={objective}
                onChange={e => setObjective(e.target.value)}
                placeholder="Describe the main goal of this role within the next 12 months..."
                className={cn(inputClasses(false), 'h-32 resize-none')}
              />
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
              <FieldLabel required>Must-Have Skills (comma separated)</FieldLabel>
              <input
                type="text"
                value={skills}
                onChange={e => setSkills(e.target.value)}
                onBlur={() => markTouched('skills')}
                placeholder="React, TypeScript, GraphQL..."
                className={inputClasses(skillsInvalid)}
              />
              {skillsInvalid && (
                <span className="label-mono text-error normal-case tracking-normal">
                  This field cannot be empty for engineering roles.
                </span>
              )}
            </div>
          </div>

          {/* 04. Interviewer Tone */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-headline-md text-on-surface">04. Interviewer Tone</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {([
                { value: 'conversational', label: 'Conversational' },
                { value: 'technical',      label: 'Technical / Strict' },
              ] as const).map(opt => {
                const active = tone === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setTone(opt.value)}
                    className={cn(
                      'flex items-center gap-3 p-4 border transition-colors duration-150 text-left',
                      active
                        ? 'border-primary-container bg-primary-container/10'
                        : 'border-outline-variant hover:bg-surface-container',
                    )}
                  >
                    <span
                      className={cn(
                        'size-5 border shrink-0 flex items-center justify-center',
                        active ? 'bg-primary-container border-primary-container' : 'border-outline-variant',
                      )}
                    >
                      {active && <span className="size-2 bg-on-primary" />}
                    </span>
                    <span className={cn('label-mono uppercase', active ? 'text-primary-fixed-dim' : 'text-on-surface')}>
                      {opt.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 05. Screening Form Builder */}
          <div className="p-8 border-b border-outline-variant">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-display text-headline-md text-on-surface">05. Screening Form Builder</h2>
            </div>
            <div className="flex flex-col lg:flex-row gap-8">
              {/* Toolbox */}
              <div className="w-full lg:w-1/3 flex flex-col gap-4">
                <span className="label-mono text-on-surface-variant">Add Form Element</span>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">
                  {FIELD_TYPES.map(ft => (
                    <button
                      key={ft.type}
                      type="button"
                      onClick={() => addField(ft.type)}
                      className="flex items-center gap-3 p-3 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim hover:bg-primary-container/5 transition-colors duration-150 label-mono justify-start"
                    >
                      <ft.icon size={18} />
                      {ft.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Canvas */}
              <div className="w-full lg:w-2/3 flex flex-col gap-2 border border-outline-variant p-4 bg-surface-container-lowest min-h-[400px]">
                {fields.length === 0 ? (
                  <div className="label-mono text-on-surface-variant text-center mt-12 border border-dashed border-outline-variant p-8">
                    Click an element type to add it to the form
                  </div>
                ) : (
                  fields.map(field => {
                    const Icon = FIELD_TYPES.find(ft => ft.type === field.type)?.icon ?? Type;
                    return (
                      <div
                        key={field.id}
                        className="flex items-center gap-3 p-3 border border-outline-variant bg-surface"
                      >
                        <Icon size={16} className="text-on-surface-variant shrink-0" />
                        <input
                          type="text"
                          value={field.label}
                          onChange={e => updateFieldLabel(field.id, e.target.value)}
                          className="flex-1 bg-transparent border-none p-0 text-body-md text-on-surface focus:outline-none focus:ring-0"
                        />
                        <span className="label-mono text-on-surface-variant shrink-0">
                          {FIELD_LABELS[field.type]}
                        </span>
                        <button
                          type="button"
                          onClick={() => removeField(field.id)}
                          className="text-error hover:bg-error/10 p-1.5 transition-colors duration-150 shrink-0"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    );
                  })
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
