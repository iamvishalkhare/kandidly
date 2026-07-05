/**
 * 404 catch-all page.
 */

import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function NotFound() {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: 'var(--background)' }}
    >
      <div className="text-center space-y-5 max-w-sm">
        {/* Logo */}
        <div className="flex justify-center mb-4">
          <div
            className="size-7 rounded-md flex items-center justify-center text-white font-bold text-sm"
            style={{ background: 'var(--accent)' }}
          >
            K
          </div>
        </div>

        <p
          className="text-7xl font-bold tabular"
          style={{ color: 'var(--text-muted)', letterSpacing: '-0.05em' }}
        >
          404
        </p>

        <div className="space-y-1">
          <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            Page not found
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            The page you're looking for doesn't exist or has been moved.
          </p>
        </div>

        <Link
          to="/console"
          className="inline-flex items-center gap-2 text-sm font-medium hover:underline"
          style={{ color: 'var(--accent)' }}
        >
          <ArrowLeft size={14} />
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
