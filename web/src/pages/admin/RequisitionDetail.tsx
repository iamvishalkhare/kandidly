/**
 * /admin/requisitions/:id — Requisition detail:
 * header + status actions, applications table, links panel.
 */

import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft, Users, Play, Pause, X, Link2, Plus,
} from 'lucide-react';
import { adminApi } from '../../lib/api';
import {
  PageHeader, Button, Card, StateBadge, Table, Thead, Th, Tbody, Tr, Td,
  EmptyState, ErrorState, Skeleton, InlineCopyField, useToast, Modal, Select,
} from '../../components/ui';
import type { RequisitionOut, AdminApplicationListOut, LinkOut } from '../../lib/types';

function scoreColor(score: number | null) {
  if (score === null) return 'var(--text-muted)';
  if (score >= 4) return '#34d399';
  if (score >= 3) return '#fbbf24';
  return '#f87171';
}

export default function RequisitionDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [createdLinks, setCreatedLinks] = useState<LinkOut[]>([]);
  const [linkModalOpen, setLinkModalOpen] = useState(false);

  const { data: req, isLoading: reqLoading, isError: reqError } = useQuery<RequisitionOut>({
    queryKey: ['requisitions', id],
    queryFn: () => adminApi.getRequisition(id!),
    enabled: !!id,
  });

  const { data: apps, isLoading: appsLoading, isError: appsError } = useQuery<AdminApplicationListOut[]>({
    queryKey: ['requisitions', id, 'applications'],
    queryFn: () => adminApi.getApplications(id!),
    enabled: !!id,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => adminApi.setRequisitionStatus(id!, status),
    onSuccess: updated => {
      qc.setQueryData(['requisitions', id], updated);
      qc.invalidateQueries({ queryKey: ['requisitions'] });
      toast(`Requisition ${updated.status}`, 'success');
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Status change failed';
      toast(msg, 'error');
    },
  });

  const linkMutation = useMutation({
    mutationFn: (kind: 'open' | 'personal') => adminApi.createLink(id!, kind),
    onSuccess: link => {
      setCreatedLinks(prev => [link, ...prev]);
      toast('Invite link created', 'success');
      setLinkModalOpen(false);
    },
    onError: () => toast('Failed to create link', 'error'),
  });

  const revokeMutation = useMutation({
    mutationFn: (linkId: string) => adminApi.revokeLink(linkId),
    onSuccess: (_, linkId) => {
      setCreatedLinks(prev => prev.filter(l => l.id !== linkId));
      toast('Link revoked', 'success');
    },
  });

  if (reqLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (reqError || !req) {
    return <ErrorState title="Couldn't load requisition" onRetry={() => qc.invalidateQueries({ queryKey: ['requisitions', id] })} />;
  }

  // Status transitions
  const nextActions: Record<string, { label: string; status: string; icon: React.ReactNode }[]> = {
    draft:  [{ label: 'Open',  status: 'open',   icon: <Play size={14} /> }],
    open:   [
      { label: 'Pause', status: 'paused', icon: <Pause size={14} /> },
      { label: 'Close', status: 'closed', icon: <X size={14} /> },
    ],
    paused: [
      { label: 'Reopen', status: 'open',   icon: <Play size={14} /> },
      { label: 'Close',  status: 'closed', icon: <X size={14} /> },
    ],
    closed: [],
  };
  const actions = nextActions[req.status] ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={req.title}
        description={req.interview_type}
        back={
          <Link
            to="/admin/requisitions"
            className="inline-flex items-center gap-1.5 text-xs hover:underline"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={13} />
            Requisitions
          </Link>
        }
        actions={
          <div className="flex items-center gap-2">
            <StateBadge state={req.status} />
            {actions.map(a => (
              <Button
                key={a.status}
                variant={a.status === 'closed' ? 'danger' : 'outline'}
                size="sm"
                leftIcon={a.icon}
                loading={statusMutation.isPending}
                onClick={() => statusMutation.mutate(a.status)}
              >
                {a.label}
              </Button>
            ))}
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Applications table */}
        <div className="lg:col-span-2 space-y-4">
          <Card padding="none">
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: 'var(--border)' }}
            >
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Applications
              </h2>
              {apps && (
                <span className="text-xs tabular" style={{ color: 'var(--text-muted)' }}>
                  {apps.length} total
                </span>
              )}
            </div>
            {appsLoading ? (
              <div className="p-5 space-y-3">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-10" />)}
              </div>
            ) : appsError ? (
              <ErrorState title="Couldn't load applications" />
            ) : !apps || apps.length === 0 ? (
              <EmptyState
                icon={<Users size={20} />}
                title="No applications yet"
                description="Share an invite link to start receiving applications."
              />
            ) : (
              <Table>
                <Thead>
                  <Th>Candidate</Th>
                  <Th>State</Th>
                  <Th>Score</Th>
                </Thead>
                <Tbody>
                  {apps.map(app => (
                    <Tr key={app.id} onClick={() => navigate(`/admin/applications/${app.id}`)}>
                      <Td>
                        <div>
                          <p className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
                            {app.candidate_name}
                          </p>
                          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                            {app.candidate_email}
                          </p>
                        </div>
                      </Td>
                      <Td><StateBadge state={app.state} /></Td>
                      <Td>
                        <span
                          className="text-sm font-semibold tabular"
                          style={{ color: scoreColor(app.overall_score) }}
                        >
                          {app.overall_score != null ? app.overall_score.toFixed(1) : '—'}
                        </span>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Links panel */}
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                Invite links
              </h3>
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Plus size={13} />}
                onClick={() => setLinkModalOpen(true)}
              >
                Create
              </Button>
            </div>
            {createdLinks.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                No links created yet. Click "Create" to generate an invite link.
              </p>
            ) : (
              <div className="space-y-3">
                {createdLinks.map(link => (
                  <div key={link.id} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span
                        className="text-xs font-medium capitalize"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {link.kind} link
                      </span>
                      <button
                        onClick={() => revokeMutation.mutate(link.id)}
                        className="text-xs hover:underline"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        Revoke
                      </button>
                    </div>
                    <InlineCopyField value={link.url} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Details */}
          <Card>
            <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
              Details
            </h3>
            <dl className="space-y-3 text-sm">
              {[
                { label: 'Interview type', value: req.interview_type },
                { label: 'Template ID',   value: <span className="font-mono text-xs">{req.form_template_id.slice(0, 8)}…</span> },
                { label: 'Rubric ID',     value: <span className="font-mono text-xs">{req.rubric_id.slice(0, 8)}…</span> },
              ].map(({ label, value }) => (
                <div key={label}>
                  <dt style={{ color: 'var(--text-muted)' }}>{label}</dt>
                  <dd className="mt-0.5 font-medium" style={{ color: 'var(--text-primary)' }}>{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      </div>

      {/* Create link modal */}
      <CreateLinkModal
        open={linkModalOpen}
        onClose={() => setLinkModalOpen(false)}
        onCreate={kind => linkMutation.mutate(kind)}
        loading={linkMutation.isPending}
      />
    </div>
  );
}

function CreateLinkModal({
  open,
  onClose,
  onCreate,
  loading,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (kind: 'open' | 'personal') => void;
  loading: boolean;
}) {
  const [kind, setKind] = useState<'open' | 'personal'>('open');
  return (
    <Modal open={open} onClose={onClose} title="Create invite link" size="sm">
      <div className="space-y-4">
        <Select
          label="Link type"
          value={kind}
          onChange={e => setKind(e.target.value as 'open' | 'personal')}
          options={[
            { value: 'open',     label: 'Open (anyone can use)' },
            { value: 'personal', label: 'Personal (single email)' },
          ]}
        />
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            loading={loading}
            leftIcon={<Link2 size={14} />}
            onClick={() => onCreate(kind)}
          >
            Create link
          </Button>
        </div>
      </div>
    </Modal>
  );
}
