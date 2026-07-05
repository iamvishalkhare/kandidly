/**
 * /admin/rubrics — Rubrics list with publish action and criteria preview drawer.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BookOpen, X, Wrench } from 'lucide-react';
import { adminApi } from '../../lib/api';
import {
  PageHeader, Card, Table, Thead, Th, Tbody, Tr, Td,
  StateBadge, Button, EmptyState, ErrorState, Skeleton, useToast, Badge,
} from '../../components/ui';
import type { RubricOut } from '../../lib/types';

export default function RubricsPage() {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [preview, setPreview] = useState<RubricOut | null>(null);

  const { data: rubrics, isLoading, isError, refetch } = useQuery<RubricOut[]>({
    queryKey: ['rubrics'],
    queryFn: adminApi.getRubrics,
  });

  const publishMutation = useMutation({
    mutationFn: (id: string) => adminApi.publishRubric(id),
    onSuccess: updated => {
      qc.setQueryData<RubricOut[]>(['rubrics'], prev =>
        prev?.map(r => (r.id === updated.id ? updated : r))
      );
      toast(`Rubric "${updated.title}" published`, 'success');
    },
    onError: () => toast('Publish failed', 'error'),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rubrics"
        description="Scoring rubrics used to evaluate candidate interviews."
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
          <ErrorState title="Couldn't load rubrics" onRetry={refetch} />
        ) : !rubrics || rubrics.length === 0 ? (
          <EmptyState
            icon={<BookOpen size={20} />}
            title="No rubrics"
            description="Rubrics are created via the API. The visual builder is coming soon."
          />
        ) : (
          <Table>
            <Thead>
              <Th>Title</Th>
              <Th>Type</Th>
              <Th>Version</Th>
              <Th>Criteria</Th>
              <Th>Status</Th>
              <Th className="w-32" />
            </Thead>
            <Tbody>
              {rubrics.map(r => (
                <Tr key={r.id}>
                  <Td>
                    <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
                      {r.title}
                    </span>
                  </Td>
                  <Td><span style={{ color: 'var(--text-muted)' }}>{r.interview_type}</span></Td>
                  <Td><span className="tabular" style={{ color: 'var(--text-muted)' }}>v{r.version}</span></Td>
                  <Td>
                    <span className="tabular text-sm" style={{ color: 'var(--text-muted)' }}>
                      {r.criteria.length}
                    </span>
                  </Td>
                  <Td><StateBadge state={r.status} /></Td>
                  <Td>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={() => setPreview(r)}>
                        Preview
                      </Button>
                      {r.status === 'draft' && (
                        <Button
                          variant="outline"
                          size="sm"
                          loading={publishMutation.isPending}
                          onClick={() => publishMutation.mutate(r.id)}
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

      {/* Criteria preview drawer */}
      {preview && (
        <div className="fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/50" onClick={() => setPreview(null)} />
          <div
            className="relative ml-auto w-full max-w-lg h-full flex flex-col border-l"
            style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
          >
            <div
              className="flex items-center justify-between px-5 py-4 border-b shrink-0"
              style={{ borderColor: 'var(--border)' }}
            >
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {preview.title}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  v{preview.version} · {preview.criteria.length} criteria
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
            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {preview.criteria.map(c => (
                <div
                  key={c.key}
                  className="rounded-lg border p-4 space-y-2"
                  style={{ borderColor: 'var(--border)', background: 'var(--background)' }}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {c.name}
                    </p>
                    <Badge color="zinc">weight {c.weight}</Badge>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{c.description}</p>
                  <div className="space-y-1 pt-1">
                    {c.level_anchors.map(a => (
                      <div key={a.level} className="flex items-start gap-2">
                        <span
                          className="size-5 rounded flex items-center justify-center text-xs font-semibold shrink-0"
                          style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
                        >
                          {a.level}
                        </span>
                        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                          {a.anchor}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
