/**
 * /apply/:applicationId/form — Dynamic form renderer.
 * Reads template_schema from ApplicationOut, renders fields by x-field type,
 * autosaves with 800ms debounce, handles resume upload + parse polling.
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload, FileText, CheckCircle2, AlertCircle, ArrowRight,
} from 'lucide-react';
import { candidateApi, publicApi } from '../../lib/api';
import { executeRecaptcha, loadRecaptcha } from '../../lib/recaptcha';
import {
  Button, Spinner,
  Skeleton, ErrorState,
} from '../../components/ui';
import { cn } from '../../lib/utils';
import type { ApplicationOut, FormFieldSchema, FormSchema } from '../../lib/types';

// ─── Field renderers ──────────────────────────────────────────────────────────

function FieldWrapper({
  field,
  children,
}: {
  field: FormFieldSchema;
  children: React.ReactNode;
}) {
  const label = field['x-label'] ?? field.title ?? '';
  const desc  = field.description;
  return (
    <div className="space-y-1.5">
      {label && (
        <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </label>
      )}
      {desc && (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{desc}</p>
      )}
      {children}
    </div>
  );
}

// Short text
function ShortTextField({ field, value, onChange }: FieldProps) {
  return (
    <FieldWrapper field={field}>
      <input
        type="text"
        value={(value as string) ?? ''}
        onChange={e => onChange(e.target.value)}
        placeholder={field['x-placeholder'] ?? ''}
        maxLength={field.maxLength}
        className="w-full rounded-md border bg-[var(--surface)] px-3 py-2 text-sm placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all duration-150"
        style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
      />
    </FieldWrapper>
  );
}

// Long text
function LongTextField({ field, value, onChange }: FieldProps) {
  const text = (value as string) ?? '';
  const max = field.maxLength;
  return (
    <FieldWrapper field={field}>
      <div className="space-y-1">
        <textarea
          value={text}
          onChange={e => onChange(e.target.value)}
          placeholder={field['x-placeholder'] ?? ''}
          maxLength={max}
          rows={4}
          className="w-full rounded-md border bg-[var(--surface)] px-3 py-2 text-sm placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all duration-150 resize-none"
          style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
        />
        {max && (
          <p className="text-xs text-right tabular" style={{ color: 'var(--text-muted)' }}>
            {text.length}/{max}
          </p>
        )}
      </div>
    </FieldWrapper>
  );
}

// Single select
function SingleSelectField({ field, value, onChange }: FieldProps) {
  const options = field.enum ?? field.items?.enum ?? [];
  return (
    <FieldWrapper field={field}>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => {
          const active = value === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(active ? '' : opt)}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-all duration-150',
                active
                  ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)]'
              )}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </FieldWrapper>
  );
}

// Multi select
function MultiSelectField({ field, value, onChange }: FieldProps) {
  const options = field.items?.enum ?? field.enum ?? [];
  const selected: string[] = Array.isArray(value) ? (value as string[]) : [];

  const toggle = (opt: string) => {
    if (selected.includes(opt)) {
      onChange(selected.filter(s => s !== opt));
    } else {
      onChange([...selected, opt]);
    }
  };

  return (
    <FieldWrapper field={field}>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => {
          const active = selected.includes(opt);
          return (
            <button
              key={opt}
              type="button"
              onClick={() => toggle(opt)}
              className={cn(
                'px-3 py-1.5 rounded-md text-sm border transition-all duration-150 flex items-center gap-1.5',
                active
                  ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)]'
              )}
            >
              {active && <CheckCircle2 size={13} />}
              {opt}
            </button>
          );
        })}
      </div>
    </FieldWrapper>
  );
}

// Scale (1..max)
function ScaleField({ field, value, onChange }: FieldProps) {
  const max = field.maximum ?? 5;
  const min = field.minimum ?? 1;
  const current = value as number | undefined;
  const ticks = Array.from({ length: max - min + 1 }, (_, i) => i + min);

  return (
    <FieldWrapper field={field}>
      <div className="flex gap-1.5 flex-wrap">
        {ticks.map(n => {
          const active = current === n;
          return (
            <button
              key={n}
              type="button"
              onClick={() => onChange(active ? null : n)}
              className={cn(
                'size-10 rounded-md text-sm font-medium border transition-all duration-150',
                active
                  ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent)]'
                  : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--text-primary)]'
              )}
            >
              {n}
            </button>
          );
        })}
      </div>
    </FieldWrapper>
  );
}

// Number
function NumberField({ field, value, onChange }: FieldProps) {
  return (
    <FieldWrapper field={field}>
      <input
        type="number"
        value={(value as number) ?? ''}
        onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))}
        min={field.minimum}
        max={field.maximum}
        className="w-full rounded-md border bg-[var(--surface)] px-3 py-2 text-sm placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all duration-150"
        style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
      />
    </FieldWrapper>
  );
}

// Boolean toggle
function BooleanField({ field, value, onChange }: FieldProps) {
  const checked = Boolean(value);
  return (
    <FieldWrapper field={field}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent',
          'transition-colors duration-150',
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
    </FieldWrapper>
  );
}

// Resume file upload
function ResumeField({
  applicationId,
  field,
  value,
  onChange,
  parseStatus,
}: FieldProps & { applicationId: string; parseStatus: string | null }) {
  const [uploading, setUploading] = useState(false);
  const [localParse, setLocalParse] = useState<string | null>(parseStatus);
  const fileRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  // Poll parse status
  useEffect(() => {
    if (localParse !== 'pending' && localParse !== 'processing') return;
    const t = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['application', applicationId] });
    }, 3000);
    return () => clearInterval(t);
  }, [localParse, applicationId, queryClient]);

  // Sync with parent
  useEffect(() => {
    setLocalParse(parseStatus);
  }, [parseStatus]);

  const handleFile = async (file: File) => {
    const allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!allowed.includes(file.type)) {
      alert('Please upload a PDF or DOCX file.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('File must be under 10 MB.');
      return;
    }
    setUploading(true);
    try {
      const res = await candidateApi.uploadResume(applicationId, file);
      onChange(res.file_id);
      setLocalParse(res.parse_status);
    } catch {
      alert('Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const hasFile = !!value;

  const parseChip = () => {
    if (!hasFile && !uploading) return null;
    if (uploading) return <span className="text-xs text-blue-400">Uploading…</span>;
    if (localParse === 'pending' || localParse === 'processing') {
      return (
        <span className="flex items-center gap-1 text-xs text-amber-400">
          <Spinner size={12} className="text-amber-400" />
          Parsing…
        </span>
      );
    }
    if (localParse === 'done') {
      return (
        <span className="flex items-center gap-1 text-xs text-emerald-400">
          <CheckCircle2 size={12} />
          Parsed successfully
        </span>
      );
    }
    if (localParse === 'failed') {
      return (
        <span className="flex items-center gap-1 text-xs text-amber-400">
          <AlertCircle size={12} />
          Couldn't parse — we'll proceed without parsing
        </span>
      );
    }
    return null;
  };

  return (
    <FieldWrapper field={field}>
      <div
        className={cn(
          'relative rounded-lg border-2 border-dashed p-6 text-center transition-all duration-150',
          hasFile ? 'border-[var(--accent)] bg-[var(--accent-muted)]' : 'border-[var(--border)] hover:border-[var(--accent)]'
        )}
        onDragOver={e => { e.preventDefault(); }}
        onDrop={e => {
          e.preventDefault();
          const f = e.dataTransfer.files[0];
          if (f) handleFile(f);
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx"
          className="sr-only"
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <Spinner size={20} />
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Uploading…</p>
          </div>
        ) : hasFile ? (
          <div className="flex flex-col items-center gap-2">
            <FileText size={24} style={{ color: 'var(--accent)' }} />
            <p className="text-sm font-medium" style={{ color: 'var(--accent)' }}>File uploaded</p>
            {parseChip()}
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="text-xs mt-1 hover:underline"
              style={{ color: 'var(--text-muted)' }}
            >
              Replace file
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload size={20} style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Drag & drop or{' '}
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="font-medium underline"
                style={{ color: 'var(--accent)' }}
              >
                browse
              </button>
            </p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>PDF or DOCX, max 10 MB</p>
          </div>
        )}
      </div>
    </FieldWrapper>
  );
}

interface FieldProps {
  field: FormFieldSchema;
  value: unknown;
  onChange: (v: unknown) => void;
}

function FieldRenderer({
  field,
  value,
  onChange,
  applicationId,
  parseStatus,
}: FieldProps & { applicationId: string; parseStatus: string | null }) {
  const type = field['x-field'] ?? field.type;

  switch (type) {
    case 'short_text': return <ShortTextField field={field} value={value} onChange={onChange} />;
    case 'long_text':  return <LongTextField  field={field} value={value} onChange={onChange} />;
    case 'single_select': return <SingleSelectField field={field} value={value} onChange={onChange} />;
    case 'multi_select':  return <MultiSelectField  field={field} value={value} onChange={onChange} />;
    case 'scale':   return <ScaleField  field={field} value={value} onChange={onChange} />;
    case 'number':  return <NumberField field={field} value={value} onChange={onChange} />;
    case 'boolean': return <BooleanField field={field} value={value} onChange={onChange} />;
    case 'file':
      return (
        <ResumeField
          field={field}
          value={value}
          onChange={onChange}
          applicationId={applicationId}
          parseStatus={parseStatus}
        />
      );
    default:
      // Fallback: treat as short text
      return <ShortTextField field={field} value={value} onChange={onChange} />;
  }
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CandidateForm() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const navigate = useNavigate();

  const { data: app, isLoading, isError, refetch } = useQuery<ApplicationOut>({
    queryKey: ['application', applicationId],
    queryFn: () => candidateApi.getApplication(applicationId!),
    enabled: !!applicationId,
  });

  // Public config carries the reCAPTCHA v3 site key (empty → challenge skipped).
  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: publicApi.getConfig,
    staleTime: Infinity,
  });
  const siteKey = config?.recaptcha_site_key ?? '';

  // Warm the reCAPTCHA script early so the token mint on submit is instant.
  useEffect(() => {
    if (siteKey) loadRecaptcha(siteKey).catch(() => {});
  }, [siteKey]);

  // Local answers mirror
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize answers from server on first load (intentionally only tracks id changes)
  const appId = app?.id;
  const appAnswers = app?.answers;
  useEffect(() => {
    if (appAnswers) {
      setAnswers(appAnswers as Record<string, unknown>);
    }
  }, [appId, appAnswers]);

  const handleChange = useCallback((key: string, val: unknown) => {
    setAnswers(prev => {
      const next = { ...prev, [key]: val };
      // Debounce autosave
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setSaveStatus('saving');
      debounceRef.current = setTimeout(async () => {
        try {
          await candidateApi.patchForm(applicationId!, { [key]: val });
          setSaveStatus('saved');
          setTimeout(() => setSaveStatus(s => (s === 'saved' ? 'idle' : s)), 2000);
        } catch {
          // Leave the value in local state; it will be re-sent on the next
          // edit and is flushed in full on submit.
          setSaveStatus('error');
        }
      }, 800);
      return next;
    });
  }, [applicationId]);

  const submitMutation = useMutation({
    mutationFn: async () => {
      // Flush any pending debounced autosave so a last-second edit isn't lost.
      // patchForm shallow-merges, so re-sending the full answers is safe and
      // guarantees the server has the latest values before we submit.
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      await candidateApi.patchForm(applicationId!, answers);
      // Mint a fresh reCAPTCHA v3 token bound to this action; the backend
      // verifies it before creating the interview + plan job. No-op (null) when
      // reCAPTCHA is unconfigured.
      const captchaToken = await executeRecaptcha(siteKey, 'form_submit');
      return candidateApi.submitForm(applicationId!, captchaToken);
    },
    onSuccess: () => {
      navigate(`/apply/${applicationId}/lobby`);
    },
  });

  // Distinguish a bot-check rejection from a generic submit failure.
  const submitErrorMessage = (): string => {
    const err = submitMutation.error as
      | { response?: { data?: { code?: string } } }
      | undefined;
    if (err?.response?.data?.code === 'captcha_failed') {
      return "Couldn't verify you're human. Please try submitting again.";
    }
    return 'Submission failed. Please try again.';
  };

  if (isLoading) {
    return (
      <FormLayout>
        <div className="space-y-6">
          {[1, 2, 3].map(i => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-1/4" />
              <Skeleton className="h-10 w-full" />
            </div>
          ))}
        </div>
      </FormLayout>
    );
  }

  if (isError || !app) {
    return (
      <FormLayout>
        <ErrorState title="Couldn't load form" onRetry={refetch} />
      </FormLayout>
    );
  }

  const schema = app.template_schema as FormSchema | null;
  if (!schema) {
    return (
      <FormLayout>
        <ErrorState title="Form not available" message="No form template is attached to this application." />
      </FormLayout>
    );
  }

  const fieldOrder: string[] =
    schema['x-kandidly']?.field_order ??
    Object.keys(schema.properties ?? {});

  const required = new Set(schema.required ?? []);

  // Check all required fields (excluding file type — they're checked differently)
  const allFilled = fieldOrder.every(key => {
    if (!required.has(key)) return true;
    const val = answers[key];
    if (val === null || val === undefined || val === '') return false;
    if (Array.isArray(val) && val.length === 0) return false;
    return true;
  });

  return (
    <FormLayout>
      {/* Header */}
      <div className="mb-8 space-y-1">
        <h1 className="text-xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
          Application Form
        </h1>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          Fill in the fields below. Your progress saves automatically.
        </p>
      </div>

      {/* Fields */}
      <div className="space-y-8">
        {fieldOrder.map(key => {
          const field = schema.properties[key];
          if (!field) return null;
          const req = required.has(key);
          return (
            <div key={key}>
              <FieldRenderer
                field={{
                  ...field,
                  'x-label': field['x-label'] ?? (field.title ? `${field.title}${req ? ' *' : ''}` : undefined),
                }}
                value={answers[key] ?? null}
                onChange={val => handleChange(key, val)}
                applicationId={applicationId!}
                parseStatus={app.resume_parse_status ?? null}
              />
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="mt-10 flex items-center justify-between">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {saveStatus === 'saving' && 'Saving…'}
          {saveStatus === 'saved' && (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 size={12} />
              Saved
            </span>
          )}
          {saveStatus === 'error' && (
            <span className="flex items-center gap-1 text-amber-400">
              <AlertCircle size={12} />
              Couldn't save — will retry
            </span>
          )}
        </span>
        <Button
          variant="primary"
          size="lg"
          disabled={!allFilled}
          loading={submitMutation.isPending}
          onClick={() => submitMutation.mutate()}
        >
          Submit & Continue
          <ArrowRight size={16} />
        </Button>
      </div>

      {submitMutation.isError && (
        <p className="text-xs text-red-400 text-right mt-2">{submitErrorMessage()}</p>
      )}

      {/* reCAPTCHA v3 requires either the (auto-injected) badge or this notice. */}
      {siteKey && (
        <p className="text-[11px] mt-4 text-right" style={{ color: 'var(--text-muted)' }}>
          Protected by reCAPTCHA —{' '}
          <a href="https://policies.google.com/privacy" target="_blank" rel="noreferrer" className="underline">Privacy</a>
          {' & '}
          <a href="https://policies.google.com/terms" target="_blank" rel="noreferrer" className="underline">Terms</a>.
        </p>
      )}
    </FormLayout>
  );
}

function FormLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen py-12 px-4"
      style={{ background: 'var(--background)' }}
    >
      <div className="max-w-xl mx-auto">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <div
            className="size-7 rounded-md flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
