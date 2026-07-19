/**
 * Guest list for invite-only requisitions (Requisition Builder — Access &
 * Invitations). Search-first: the invited candidates are never listed in
 * full — a debounced autocomplete over name + email shows the top 3 matches
 * (with delivery + pipeline status and resend/revoke), which keeps the panel
 * identical at 10 invites or 10,000. Inline single add and a bulk CSV/XLSX
 * upload modal over a blurred backdrop handle getting candidates in.
 */

import { useEffect, useRef, useState } from 'react';
import { FileSpreadsheet, Mail, Plus, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { Spinner, useToast } from '../../components/ui';
import {
  useInviteMutations,
  useInvites,
  type InvitesMutationWire,
  type InviteWire,
} from '../../lib/consoleApi';

const SAMPLE_CSV =
  'data:text/csv;charset=utf-8,' +
  encodeURIComponent('email,first_name,last_name\njordan@example.com,Jordan,Lee\n');

const STATUS_STYLES: Record<InviteWire['status'], string> = {
  invited: 'text-on-surface-variant border-outline-variant',
  claimed: 'text-primary-fixed-dim border-primary-container bg-primary-container/10',
  completed: 'text-green-700 border-green-300 bg-green-50',
};

const DELIVERY_LABELS: Record<InviteWire['email_status'], string> = {
  queued: 'Email queued',
  sent: 'Email sent',
  failed: 'Email failed',
};

function mutationSummary(result: InvitesMutationWire): string {
  const parts = [`${result.added} invited`];
  if (result.duplicates) parts.push(`${result.duplicates} already invited`);
  if (result.invalid.length) parts.push(`${result.invalid.length} invalid`);
  return parts.join(' · ');
}

export default function InvitePanel({ requisitionId, live }: { requisitionId: string; live: boolean }) {
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  // Debounce keystrokes so autocomplete doesn't fire a request per character.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isPending } = useInvites(requisitionId, query);
  const { add, importFile, revoke, resend } = useInviteMutations(requisitionId);

  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [modalOpen, setModalOpen] = useState(false);

  const submitAdd = () => {
    if (!email.trim()) return;
    add.mutate([{ email: email.trim(), first_name: firstName.trim(), last_name: lastName.trim() }], {
      onSuccess: result => {
        if (result.invalid.length) {
          toast('That doesn’t look like a valid email address.', 'error');
          return;
        }
        if (result.added === 0) {
          toast('That candidate is already invited.', 'error');
          return;
        }
        setEmail('');
        setFirstName('');
        setLastName('');
        toast(live ? 'Invitation email on its way.' : 'Invite saved — emails go out on deploy.');
      },
      onError: () => toast('Could not add the invite. Please retry.', 'error'),
    });
  };

  const results = query ? (data?.items ?? []) : [];

  return (
    <div className="mt-4 border border-outline-variant">
      <div className="flex items-center justify-between gap-3 p-3 border-b border-outline-variant bg-surface-container/40">
        <span className="label-mono text-on-surface-variant">
          Invited candidates{data ? ` — ${data.total}` : ''}
        </span>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim hover:bg-primary-container/5 transition-colors duration-150 label-mono"
        >
          <Upload size={14} />
          Bulk upload
        </button>
      </div>

      {/* Inline add */}
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto] gap-2 p-3 border-b border-outline-variant">
        <input
          type="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitAdd()}
          placeholder="candidate@company.com"
          className="px-3 py-2 border border-outline-variant bg-surface text-body-md text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary-container"
        />
        <input
          value={firstName}
          onChange={e => setFirstName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitAdd()}
          placeholder="First name"
          className="px-3 py-2 border border-outline-variant bg-surface text-body-md text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary-container"
        />
        <input
          value={lastName}
          onChange={e => setLastName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submitAdd()}
          placeholder="Last name"
          className="px-3 py-2 border border-outline-variant bg-surface text-body-md text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary-container"
        />
        <button
          type="button"
          onClick={submitAdd}
          disabled={add.isPending || !email.trim()}
          className="flex items-center justify-center gap-2 px-4 py-2 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim hover:bg-primary-container/5 transition-colors duration-150 label-mono disabled:opacity-40 disabled:pointer-events-none"
        >
          {add.isPending ? <Spinner size={14} /> : <Plus size={14} />}
          Invite
        </button>
      </div>

      {/* Search-first lookup */}
      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner size={18} />
        </div>
      ) : data?.total === 0 ? (
        <p className="p-4 text-body-md text-on-surface-variant">
          No candidates invited yet. Only invited email addresses will be able to start this
          interview.
        </p>
      ) : (
        <div className="p-3 space-y-2">
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none"
            />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search invited candidates by name or email…"
              className="w-full pl-9 pr-3 py-2 border border-outline-variant bg-surface text-body-md text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary-container"
              aria-label="Search invited candidates"
            />
          </div>

          {!query ? (
            <p className="text-body-md text-on-surface-variant px-1">
              Type a name or email to look up an invited candidate. Top 3 matches are shown.
            </p>
          ) : results.length === 0 ? (
            <p className="text-body-md text-on-surface-variant px-1">
              No invited candidate matches “{query}”.
            </p>
          ) : (
            <ul className="border border-outline-variant">
              {results.map(invite => (
                <li
                  key={invite.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 border-b border-outline-variant last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-body-md text-on-surface truncate">
                      {[invite.first_name, invite.last_name].filter(Boolean).join(' ') || '—'}
                    </p>
                    <p className="text-body-md text-on-surface-variant truncate">{invite.email}</p>
                  </div>
                  <span
                    className={cn(
                      'px-2 py-0.5 border label-mono uppercase',
                      STATUS_STYLES[invite.status],
                    )}
                  >
                    {invite.status}
                  </span>
                  <span
                    className={cn(
                      'flex items-center gap-1.5 label-mono',
                      invite.email_status === 'failed' ? 'text-red-600' : 'text-on-surface-variant',
                    )}
                    title={invite.last_emailed_at ?? undefined}
                  >
                    <Mail size={13} />
                    {DELIVERY_LABELS[invite.email_status]}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      title="Resend invitation email"
                      onClick={() =>
                        resend.mutate(invite.id, {
                          onSuccess: () =>
                            toast(live ? 'Invitation email resent.' : 'Queued — sends on deploy.'),
                        })
                      }
                      className="p-1.5 text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150"
                    >
                      <RefreshCw size={15} />
                    </button>
                    <button
                      type="button"
                      title="Revoke access"
                      onClick={() =>
                        revoke.mutate(invite.id, { onSuccess: () => toast('Access revoked.') })
                      }
                      className="p-1.5 text-on-surface-variant hover:text-red-600 transition-colors duration-150"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {modalOpen && (
        <BulkInviteModal
          busy={importFile.isPending}
          result={importFile.data ?? null}
          error={importFile.isError}
          onUpload={file => importFile.mutate(file)}
          onClose={() => {
            importFile.reset();
            setModalOpen(false);
          }}
        />
      )}
    </div>
  );
}

/* ── bulk upload modal ────────────────────────────────────────────────────── */

function BulkInviteModal({
  busy,
  result,
  error,
  onUpload,
  onClose,
}: {
  busy: boolean;
  result: InvitesMutationWire | null;
  error: boolean;
  onUpload: (file: File) => void;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const pick = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onUpload(file);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Bulk invite candidates"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-surface border border-outline-variant p-5 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="font-display text-headline-md text-on-surface">Bulk invite candidates</h3>
            <p className="text-body-md text-on-surface-variant mt-1">
              Upload a .csv or .xlsx with three columns — email, first name, last name. A header
              row is optional.{' '}
              <a
                href={SAMPLE_CSV}
                download="candidates-sample.csv"
                className="underline underline-offset-2 text-primary-fixed-dim"
              >
                Download a sample
              </a>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-on-surface-variant hover:text-on-surface transition-colors duration-150"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={e => {
            pick(e.target.files);
            e.target.value = '';
          }}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={e => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault();
            setDragOver(false);
            pick(e.dataTransfer.files);
          }}
          disabled={busy}
          className={cn(
            'w-full flex flex-col items-center gap-2 border border-dashed p-8 transition-colors duration-150',
            dragOver
              ? 'border-primary-container bg-primary-container/10 text-primary-fixed-dim'
              : 'border-outline-variant text-on-surface-variant hover:border-primary-container hover:text-primary-fixed-dim',
          )}
        >
          {busy ? <Spinner size={20} /> : <FileSpreadsheet size={22} />}
          <span className="label-mono uppercase">
            {busy ? 'Importing…' : 'Drop a file here or click to browse'}
          </span>
        </button>

        {error && (
          <p className="text-body-md text-red-600">
            The file could not be imported. Check it is a .csv or .xlsx under 1&nbsp;MB and try
            again.
          </p>
        )}
        {result && (
          <div className="space-y-2">
            <p className="text-body-md text-on-surface">{mutationSummary(result)}</p>
            {result.invalid.length > 0 && (
              <ul className="max-h-32 overflow-y-auto border border-outline-variant p-2 space-y-1">
                {result.invalid.map(row => (
                  <li key={row.row} className="text-body-md text-on-surface-variant">
                    Row {row.row}: {row.reason}
                  </li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-outline-variant hover:border-primary-container hover:text-primary-fixed-dim transition-colors duration-150 label-mono"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
