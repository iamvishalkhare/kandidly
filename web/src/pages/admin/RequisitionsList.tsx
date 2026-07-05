/**
 * /admin/requisitions — Requisitions list with "New requisition" modal wizard.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Briefcase, ArrowRight, ChevronLeft } from 'lucide-react';
import { adminApi } from '../../lib/api';
import {
  PageHeader, Button, Card, Table, Thead, Th, Tbody, Tr, Td,
  StateBadge, Modal, Input, Select, Skeleton, EmptyState, ErrorState,
  useToast,
} from '../../components/ui';
import type { RequisitionOut, FormTemplateOut, RubricOut } from '../../lib/types';

// ─── New Requisition Wizard ────────────────────────────────────────────────────

interface WizardProps {
  open: boolean;
  onClose: () => void;
}

function NewRequisitionModal({ open, onClose }: WizardProps) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2>(1);
  const [form, setForm] = useState({
    title: '',
    interview_type: '',
    form_template_id: '',
    rubric_id: '',
  });

  const { data: templates, isLoading: tplLoading } = useQuery<FormTemplateOut[]>({
    queryKey: ['form-templates'],
    queryFn: adminApi.getFormTemplates,
    enabled: open,
  });

  const { data: rubrics, isLoading: rubLoading } = useQuery<RubricOut[]>({
    queryKey: ['rubrics'],
    queryFn: adminApi.getRubrics,
    enabled: open,
  });

  const publishedTemplates = templates?.filter(t => t.status === 'published') ?? [];
  const publishedRubrics   = rubrics?.filter(r => r.status === 'published') ?? [];

  const createMutation = useMutation({
    mutationFn: () => adminApi.createRequisition(form),
    onSuccess: req => {
      qc.invalidateQueries({ queryKey: ['requisitions'] });
      toast('Requisition created', 'success');
      handleClose();
      navigate(`/admin/requisitions/${req.id}`);
    },
    onError: () => toast('Failed to create requisition', 'error'),
  });

  const reset = () => {
    setStep(1);
    setForm({ title: '', interview_type: '', form_template_id: '', rubric_id: '' });
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const step1Valid = form.title.trim() && form.interview_type.trim();
  const step2Valid = form.form_template_id && form.rubric_id;

  return (
    <Modal open={open} onClose={handleClose} title="New Requisition" size="md">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-6">
        {([1, 2] as const).map(n => (
          <div key={n} className="flex items-center gap-2">
            <div
              className="size-6 rounded-full flex items-center justify-center text-xs font-semibold transition-colors"
              style={
                step === n
                  ? { background: 'var(--accent)', color: 'white' }
                  : n < step
                  ? { background: 'rgba(139,124,246,0.2)', color: 'var(--accent)' }
                  : { background: 'var(--surface-hover)', color: 'var(--text-muted)' }
              }
            >
              {n}
            </div>
            <span
              className="text-xs font-medium"
              style={{ color: step === n ? 'var(--text-primary)' : 'var(--text-muted)' }}
            >
              {n === 1 ? 'Details' : 'Template & Rubric'}
            </span>
            {n < 2 && <div className="w-8 h-px mx-1" style={{ background: 'var(--border)' }} />}
          </div>
        ))}
      </div>

      {step === 1 ? (
        <div className="space-y-4">
          <Input
            label="Job title"
            placeholder="e.g. Senior Software Engineer"
            value={form.title}
            onChange={e => setForm({ ...form, title: e.target.value })}
          />
          <Input
            label="Interview type"
            placeholder="e.g. software_engineering"
            value={form.interview_type}
            onChange={e => setForm({ ...form, interview_type: e.target.value })}
            hint="Used to match templates and rubrics."
          />
          <div className="flex justify-end pt-2">
            <Button
              variant="primary"
              disabled={!step1Valid}
              onClick={() => setStep(2)}
            >
              Next
              <ArrowRight size={14} />
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {tplLoading || rubLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : (
            <>
              {publishedTemplates.length === 0 ? (
                <div
                  className="rounded-lg border p-4 text-center text-sm"
                  style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)', color: 'var(--text-muted)' }}
                >
                  No published form templates.{' '}
                  <Link to="/admin/forms" className="underline" style={{ color: 'var(--accent)' }}>
                    Create & publish one first.
                  </Link>
                </div>
              ) : (
                <Select
                  label="Form template"
                  placeholder="Select a template…"
                  value={form.form_template_id}
                  onChange={e => setForm({ ...form, form_template_id: e.target.value })}
                  options={publishedTemplates.map(t => ({
                    value: t.id,
                    label: `${t.title} (v${t.version})`,
                  }))}
                />
              )}

              {publishedRubrics.length === 0 ? (
                <div
                  className="rounded-lg border p-4 text-center text-sm"
                  style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)', color: 'var(--text-muted)' }}
                >
                  No published rubrics.{' '}
                  <Link to="/admin/rubrics" className="underline" style={{ color: 'var(--accent)' }}>
                    Create & publish one first.
                  </Link>
                </div>
              ) : (
                <Select
                  label="Rubric"
                  placeholder="Select a rubric…"
                  value={form.rubric_id}
                  onChange={e => setForm({ ...form, rubric_id: e.target.value })}
                  options={publishedRubrics.map(r => ({
                    value: r.id,
                    label: `${r.title} (v${r.version})`,
                  }))}
                />
              )}
            </>
          )}

          <div className="flex items-center justify-between pt-2">
            <Button variant="ghost" size="sm" onClick={() => setStep(1)} leftIcon={<ChevronLeft size={14} />}>
              Back
            </Button>
            <Button
              variant="primary"
              disabled={!step2Valid}
              loading={createMutation.isPending}
              onClick={() => createMutation.mutate()}
            >
              Create Requisition
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function RequisitionsList() {
  const [modalOpen, setModalOpen] = useState(false);
  const navigate = useNavigate();

  const { data: reqs, isLoading, isError, refetch } = useQuery<RequisitionOut[]>({
    queryKey: ['requisitions'],
    queryFn: adminApi.getRequisitions,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Requisitions"
        description="All open positions and hiring pipelines."
        actions={
          <Button variant="primary" size="sm" leftIcon={<Plus size={14} />} onClick={() => setModalOpen(true)}>
            New Requisition
          </Button>
        }
      />

      <Card padding="none">
        {isLoading ? (
          <div className="p-5 space-y-3">
            {[1, 2, 3].map(i => <Skeleton key={i} className="h-12" />)}
          </div>
        ) : isError ? (
          <ErrorState title="Couldn't load requisitions" onRetry={refetch} />
        ) : !reqs || reqs.length === 0 ? (
          <EmptyState
            icon={<Briefcase size={20} />}
            title="No requisitions yet"
            description="Create your first requisition to start hiring."
            action={
              <Button variant="primary" size="sm" leftIcon={<Plus size={14} />} onClick={() => setModalOpen(true)}>
                New Requisition
              </Button>
            }
          />
        ) : (
          <Table>
            <Thead>
              <Th>Title</Th>
              <Th>Type</Th>
              <Th>Status</Th>
              <Th className="w-20" />
            </Thead>
            <Tbody>
              {reqs.map(req => (
                <Tr key={req.id} onClick={() => navigate(`/admin/requisitions/${req.id}`)}>
                  <Td>
                    <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                      {req.title}
                    </span>
                  </Td>
                  <Td>
                    <span style={{ color: 'var(--text-muted)' }}>{req.interview_type}</span>
                  </Td>
                  <Td><StateBadge state={req.status} /></Td>
                  <Td>
                    <span className="text-xs" style={{ color: 'var(--accent)' }}>View →</span>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>

      <NewRequisitionModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}
