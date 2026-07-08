/**
 * /apply/:applicationId/done — Calm thank-you page.
 * No scores shown.
 */

import { CheckCircle2 } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

export default function CandidateDone() {
  const [params] = useSearchParams();
  const fromInterview = params.get('from') === 'interview';

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: 'var(--background)' }}
    >
      <div className="max-w-sm mx-auto text-center space-y-6">
        {/* Logo */}
        <div className="flex justify-center mb-4">
          <div
            className="size-7 rounded-md flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
        </div>

        <div
          className="size-16 rounded-2xl flex items-center justify-center mx-auto"
          style={{ background: 'rgba(16,185,129,0.1)' }}
        >
          <CheckCircle2 size={32} className="text-emerald-400" />
        </div>

        <div className="space-y-2">
          <h1 className="text-xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            {fromInterview ? 'Your interview is complete' : 'Thank you for your time'}
          </h1>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {fromInterview
              ? 'Thanks for completing your interview. The hiring team will review your submission and be in touch with next steps.'
              : 'Your application has been received. The hiring team will review your submission and be in touch with next steps.'}
          </p>
        </div>

        <div
          className="rounded-xl border p-5 text-left space-y-3"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>
            What happens next
          </p>
          {[
            'Your interview is being processed.',
            'The hiring team will review your answers and interview.',
            'You\'ll hear back via email within a few business days.',
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <span
                className="size-5 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5"
                style={{ background: 'var(--surface-hover)', color: 'var(--text-muted)' }}
              >
                {i + 1}
              </span>
              {item}
            </div>
          ))}
        </div>

        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          You may now close this window.
        </p>
      </div>
    </div>
  );
}
