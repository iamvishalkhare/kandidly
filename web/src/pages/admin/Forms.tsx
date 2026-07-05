/**
 * /admin/forms — Form templates list with publish action and JSON preview drawer.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, X, Wrench } from 'lucide-react';
import { adminApi } from '../../lib/api';
import {
  PageHeader, Card, Table, Thead, Th, Tbody, Tr, Td,
  StateBadge, Button, EmptyState, ErrorState, Skeleton, useToast,
} from '../../components/ui';
import type { FormTemplateOut } from '../../lib/types';

export default function FormsPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [preview, setPreview] = useState<FormTemplateOut | null>(null);

  const { data: templates, isLoading, isError, refetch } = useQuery<FormTemplateOut[]>({
    queryKey: ['form-templates'],
    queryFn: adminApi.getFormTemplates,
  });

  const publishMutation = useMutation({
    mutationFn: (id: string) => adminApi.publishTemplate(id),
    onSuccess: updated => {
      qc.setQueryData<FormTemplateOut[]>(['form-templates'], prev =>
        prev?.map(t => (t.id === updated.id ? updated : t))
      );
      toast(`Template "${updated.title}" published`, 'success');
    },
    onError: () => toast('Publish failed', 'error'),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Form Templates"
        description="KYI form templates used by requisitions."
        actions={
          <div
            className="rounded-lg border px-3 py-1.5 text-xs flex items-center gap-1.5"
            style={{ borderColor: 'rgba(245,158,11,0.2)', background: 'rgba(245,158,11,0.05)', color: '#fbbf24' }}
          >
            <Wrench size={12} />
            Visual builder coming soon
          </div>
        }
      />

      <Card padding="none">
        {isLoading ? (
          <div className="p-5 space-y-3">
            {[1, 2].map(i => <Skeleton key={i} className="h-12" />)}
          </div>
        ) : isError ? (
          <ErrorState title="Couldn't load templates" onRetry={refetch} />
        ) : !templates || templates.length === 0 ? (
          <EmptyState
            icon={<FileText size={20} />}
            title="No form templates"
            description="Templates are created via the API. The visual builder is coming soon."
          />
        ) : (
          <Table>
            <Thead>
              <Th>Title</Th>
              <Th>Type</Th>
              <Th>Version</Th>
              <Th>Status</Th>
              <Th className="w-32" />
            </Thead>
            <Tbody>
              {templates.map(t => (
                <Tr key={t.id}>
                  <Td>
                    <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                      {t.title}
                    </span>
                  </Td>
                  <Td><span style={{ color: 'var(--text-muted)' }}>{t.interview_type}</span></Td>
                  <Td><span className="tabular" style={{ color: 'var(--text-muted)' }}>v{t.version}</span></Td>
                  <Td><StateBadge state={t.status} /></Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPreview(t)}
                      >
                        Preview
                      </Button>
                      {t.status === 'draft' && (
                        <Button
                          variant="outline"
                          size="sm"
                          loading={publishMutation.isPending}
                          onClick={() => publishMutation.mutate(t.id)}
                        >
                          Publish
                        </Button>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>

      {/* JSON preview drawer */}
      {preview && (
        <div className="fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setPreview(null)} />
          <div
            className="relative ml-auto w-full max-w-lg h-full flex flex-col border-l"
            style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
          >
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: 'var(--border)' }}
            >
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {preview.title}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  v{preview.version} · {preview.status}
                </p>
              </div>
              <button
                onClick={() => setPreview(null)}
                className="rounded-md p-1 transition-colors hover:bg-[var(--surface-hover)]"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              <pre
                className="text-xs rounded-lg p-4 overflow-x-auto"
                style={{
                  background: 'var(--background)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {JSON.stringify(preview.schema, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
