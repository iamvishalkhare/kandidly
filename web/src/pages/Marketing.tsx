/**
 * Public marketing landing page ("/") — The Brutalist Blueprint.
 * Ported from docs/design/index.html into the app's own token set.
 */

import { Link } from 'react-router-dom';
import { ArrowRight, ListChecks, Mic, ClipboardCheck, ShieldCheck } from 'lucide-react';
import { cn } from '../lib/utils';

const NAV_LINKS = [
  { label: 'Platform', href: '#platform' },
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#sequence' },
];

const WAVEFORM = [
  18, 32, 24, 48, 62, 40, 70, 55, 36, 80, 64, 44, 58, 30, 22, 46, 68, 84, 52, 38,
  26, 60, 74, 50, 34, 66, 42, 78, 56, 28, 88, 72, 48, 60, 36, 54, 44, 70, 58, 40,
];

const STATS: { value: string; label: string; accent?: boolean }[] = [
  { value: '1,248', label: 'Interviews conducted' },
  { value: '3.4×', label: 'Faster screening cycles' },
  { value: '0', label: 'Scheduling emails sent', accent: true },
  { value: '96%', label: 'Candidate completion' },
];

const FEATURES = [
  {
    n: '01', icon: ListChecks, title: 'Rubric-first evaluation',
    body: "Every answer is scored against weighted criteria you define — not an interviewer's mood.",
  },
  {
    n: '02', icon: Mic, title: 'Adaptive voice agent',
    body: 'Follows up, probes depth, and moves on — a real conversation, available any hour.',
  },
  {
    n: '03', icon: ClipboardCheck, title: 'Quote-backed reports',
    body: 'Scores cite verbatim transcript evidence. Trust the number or audit it in one click.',
  },
  {
    n: '04', icon: ShieldCheck, title: 'Integrity built in',
    body: 'Consent-gated proctoring, identity checks, and DPDP-compliant retention by default.',
  },
];

const STEPS: { n: string; title: string; body: string; cta?: { label: string; to: string }; note?: string }[] = [
  {
    n: '01', title: 'Define',
    body: 'Set the role, screening form, and weighted rubric in the requisition builder. Publish when the weights hit 100%.',
    cta: { label: 'Open builder', to: '/admin/requisitions' },
  },
  {
    n: '02', title: 'Deploy',
    body: "Share one invite link. Candidates apply, upload a resume, and take the voice interview whenever they're ready.",
    note: 'kandid.ly/i/ENG-001',
  },
  {
    n: '03', title: 'Decide',
    body: 'Scored reports with transcript evidence land in your console. Review, override, and shortlist in minutes.',
    cta: { label: 'View console', to: '/admin' },
  },
];

function TopNav() {
  return (
    <nav className="sticky top-0 z-50 h-16 border-b border-outline-variant bg-surface-container-lowest">
      <div className="mx-auto max-w-[1440px] h-full flex items-stretch justify-between border-x border-outline-variant">
        <Link to="/" className="flex items-center gap-2 px-4 md:px-8 border-r border-outline-variant">
          <span className="size-2.5 bg-primary-container" />
          <span className="font-display text-headline-md font-bold tracking-tight text-primary-fixed-dim">KANDIDLY</span>
        </Link>
        <div className="hidden md:flex items-stretch">
          {NAV_LINKS.map((item, i) => (
            <a
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center px-5 label-mono transition-colors duration-150',
                i === 0
                  ? 'text-primary-fixed-dim border-b-2 border-primary-container'
                  : 'text-on-surface-variant hover:bg-surface-container hover:text-on-surface'
              )}
            >
              {item.label}
            </a>
          ))}
        </div>
        <Link
          to="/admin"
          className="flex items-center gap-2 px-4 md:px-8 border-l border-outline-variant label-mono text-on-surface hover:bg-primary-container hover:text-on-primary-container transition-colors duration-150"
        >
          Console login
          <ArrowRight size={14} />
        </Link>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section id="platform" className="grid grid-cols-1 lg:grid-cols-2 border-b border-outline-variant">
      {/* Left: copy */}
      <div className="border-b lg:border-b-0 lg:border-r border-outline-variant p-4 md:p-12 flex flex-col justify-center gap-8">
        <div className="inline-flex items-center gap-3 self-start border border-outline-variant px-3 py-2">
          <span className="size-2 bg-primary-container blink" />
          <span className="label-mono text-on-surface-variant">AI voice interviewer // v1.0</span>
        </div>
        <h1 className="font-display text-headline-lg-mobile md:text-display-lg font-bold text-on-surface">
          Engineered<br />interviews.
        </h1>
        <p className="text-body-lg text-on-surface-variant max-w-md border-l-2 border-primary-container pl-4">
          Kandidly runs structured voice interviews for every candidate — same questions, same rubric, zero
          scheduling. Your team reads scored, quote-backed reports instead of sitting in screens.
        </p>
        <div className="flex flex-wrap gap-px bg-outline-variant self-start border border-outline-variant">
          <Link
            to="/admin"
            className="px-8 py-4 bg-primary-container text-on-primary-container label-mono font-bold hover:bg-surface-container-lowest hover:text-primary-fixed-dim transition-colors duration-150"
          >
            Start hiring
          </Link>
          <a
            href="#sequence"
            className="px-8 py-4 bg-surface-container-lowest text-on-surface label-mono hover:bg-surface-container transition-colors duration-150"
          >
            See the sequence
          </a>
        </div>
        <p className="label-mono text-on-surface-variant/60">No credit card. First 10 interviews free.</p>
      </div>

      {/* Right: live console wireframe (pure CSS, no images) */}
      <div className="hidden lg:flex flex-col bg-surface min-h-[560px]">
        <div className="h-10 flex items-center justify-between px-4 border-b border-outline-variant">
          <span className="label-mono text-on-surface-variant">SESSION // CAN-8921A</span>
          <span className="label-mono text-primary-fixed-dim flex items-center gap-2">
            <span className="size-2 bg-primary-container blink" />REC 00:42:17
          </span>
        </div>
        <div className="h-24 border-b border-outline-variant px-4 flex items-end gap-[3px] py-3">
          {WAVEFORM.map((h, i) => (
            <div
              key={i}
              className={cn('flex-1', i >= WAVEFORM.length - 8 ? 'bg-primary-container' : 'bg-outline-variant')}
              style={{ height: `${h}%` }}
            />
          ))}
        </div>
        <div className="flex-1 p-5 font-mono text-label-sm leading-relaxed space-y-4 overflow-hidden">
          <p>
            <span className="text-primary-fixed-dim">AGENT &gt;</span>{' '}
            <span className="text-on-surface">Walk me through the worst production incident you owned end to end.</span>
          </p>
          <p>
            <span className="text-on-surface-variant">CAND&nbsp; &gt;</span>{' '}
            <span className="text-on-surface-variant">
              We had a race condition in the payment retry queue — two workers claimed the same job because the
              lease…
            </span>
          </p>
          <p>
            <span className="text-primary-fixed-dim">AGENT &gt;</span>{' '}
            <span className="text-on-surface">How did you prove the lease was the root cause and not the idempotency key?</span>
          </p>
          <p className="text-on-surface-variant/50">&gt; MAPPING RESPONSE TO RUBRIC · DEBUGGING_DEPTH</p>
        </div>
        <div className="grid grid-cols-3 gap-px bg-outline-variant border-t border-outline-variant">
          <div className="bg-surface-container-lowest p-4">
            <p className="label-mono text-on-surface-variant mb-1">Signal</p>
            <p className="font-display text-headline-md text-on-surface">Strong</p>
          </div>
          <div className="bg-surface-container-lowest p-4">
            <p className="label-mono text-on-surface-variant mb-1">Rubric</p>
            <p className="font-display text-headline-md text-on-surface">4<span className="text-on-surface-variant">/6</span></p>
          </div>
          <div className="bg-surface-container-lowest p-4">
            <p className="label-mono text-on-surface-variant mb-1">Score</p>
            <p className="font-display text-headline-md text-primary-fixed-dim">Pending</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function ProofStrip() {
  return (
    <section className="border-b border-outline-variant">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-outline-variant">
        {STATS.map(s => (
          <div key={s.label} className="bg-surface-container-lowest p-6 md:p-8">
            <p className={cn('font-display text-headline-lg', s.accent ? 'text-primary-fixed-dim' : 'text-on-surface')}>
              {s.value}
            </p>
            <p className="label-mono text-on-surface-variant mt-2">{s.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="features" className="border-b border-outline-variant">
      <div className="p-4 border-b border-outline-variant bg-surface">
        <h2 className="label-mono text-on-surface">// CORE_INFRASTRUCTURE</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-px bg-outline-variant">
        {FEATURES.map(f => (
          <div
            key={f.n}
            className="group bg-surface-container-lowest h-[300px] p-6 flex flex-col justify-between hover:bg-surface transition-colors duration-150"
          >
            <div className="flex justify-between items-start">
              <span className="font-mono text-label-sm text-on-surface-variant/60">{f.n}</span>
              <f.icon size={20} className="text-primary-fixed-dim group-hover:translate-x-1 transition-transform duration-150" />
            </div>
            <div>
              <h3 className="font-display text-headline-md text-on-surface mb-2">{f.title}</h3>
              <p className="text-body-md text-on-surface-variant">{f.body}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Sequence() {
  return (
    <section id="sequence" className="border-b border-outline-variant">
      <div className="p-4 border-b border-outline-variant bg-surface">
        <h2 className="label-mono text-on-surface">// DEPLOYMENT_SEQUENCE</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-px bg-outline-variant">
        {STEPS.map(s => (
          <div key={s.n} className="bg-surface-container-lowest p-6 md:p-8 flex flex-col gap-4">
            <span className="font-display text-display-lg text-outline-variant leading-none">{s.n}</span>
            <h3 className="font-display text-headline-md text-on-surface">{s.title}</h3>
            <p className="text-body-md text-on-surface-variant">{s.body}</p>
            {s.cta && (
              <Link to={s.cta.to} className="mt-auto self-start label-mono text-primary-fixed-dim hover:text-on-surface transition-colors duration-150">
                {s.cta.label} →
              </Link>
            )}
            {s.note && <span className="mt-auto label-mono text-on-surface-variant/60">{s.note}</span>}
          </div>
        ))}
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="border-b border-outline-variant bg-surface">
      <div className="p-8 md:p-16 flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div>
          <p className="label-mono text-on-surface-variant mb-4">// READY_STATE</p>
          <h2 className="font-display text-headline-lg-mobile md:text-headline-lg text-on-surface max-w-xl">
            Standardize the interview.<br /><span className="text-primary-fixed-dim">Keep the judgment.</span>
          </h2>
        </div>
        <Link
          to="/admin"
          className="self-start md:self-auto px-10 py-5 bg-primary-container text-on-primary-container label-mono font-bold border border-primary-container hover:bg-transparent hover:text-primary-fixed-dim transition-colors duration-150"
        >
          Deploy Kandidly
        </Link>
      </div>
    </section>
  );
}

function MarketingFooter() {
  return (
    <footer className="mx-auto max-w-[1440px] border-x border-b border-outline-variant">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 p-8">
        <div className="flex items-center gap-2">
          <span className="size-2.5 bg-primary-container" />
          <span className="font-display text-headline-md font-bold tracking-tight text-primary-fixed-dim">KANDIDLY</span>
        </div>
        <div className="flex flex-wrap gap-6">
          {['Privacy', 'Terms', 'Security', 'Status'].map(l => (
            <a key={l} href="#" className="label-mono text-on-surface-variant hover:text-primary-fixed-dim transition-colors duration-150">
              {l}
            </a>
          ))}
        </div>
        <p className="label-mono text-on-surface-variant/60">© 2026 Kandidly. All systems nominal.</p>
      </div>
    </footer>
  );
}

export default function Marketing() {
  return (
    <div className="bg-surface-container-lowest text-on-surface font-body antialiased">
      <TopNav />
      <main className="mx-auto max-w-[1440px] border-x border-outline-variant">
        <Hero />
        <ProofStrip />
        <Features />
        <Sequence />
        <CtaBand />
      </main>
      <MarketingFooter />
    </div>
  );
}
