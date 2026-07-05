/** @type {import('tailwindcss').Config} */

// The Brutalist Blueprint — token source: docs/design/DESIGN.md
// Rectilinear (0px radius), no shadows, 1px outline-variant borders,
// cobalt (#2e5bff) as the sole functional accent.
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Blueprint tokens (M3 naming, matches DESIGN.md)
        surface:                     '#11131c',
        'surface-bright':            '#373943',
        'surface-container-lowest':  '#0c0e17',
        'surface-container-low':     '#191b24',
        'surface-container':         '#1d1f29',
        'surface-container-high':    '#282933',
        'surface-container-highest': '#33343e',
        'on-surface':                '#e2e1ef',
        'on-surface-variant':        '#c4c5d9',
        outline:                     '#8e90a2',
        'outline-variant':           '#434656',
        'on-primary':                '#002388',
        'primary-fixed':             '#dde1ff',
        'primary-fixed-dim':         '#b8c3ff',
        'primary-container':         '#2e5bff',
        'on-primary-container':      '#efefff',
        'inverse-primary':           '#124af0',
        error:                       '#ffb4ab',
        'on-error':                  '#690005',
        'error-container':           '#93000a',
        'on-error-container':        '#ffdad6',

        // Legacy var-backed names — existing pages use these; the vars in
        // index.css now resolve to the blueprint palette.
        background:      'var(--background)',
        'surface-hover': 'var(--surface-hover)',
        accent:          'var(--accent)',
        'accent-muted':  'var(--accent-muted)',
        'text-primary':   'var(--text-primary)',
        'text-secondary': 'var(--text-secondary)',
        'text-muted':     'var(--text-muted)',
        primary: {
          DEFAULT: 'var(--accent)',
          foreground: '#efefff',
        },
        secondary: {
          DEFAULT: 'var(--surface)',
          foreground: 'var(--text-primary)',
        },
        destructive: {
          DEFAULT: '#93000a',
          foreground: '#ffdad6',
        },
        muted: {
          DEFAULT: 'var(--surface)',
          foreground: 'var(--text-muted)',
        },
        card: {
          DEFAULT: 'var(--surface)',
          foreground: 'var(--text-primary)',
        },
        foreground: 'var(--text-primary)',
        border: 'var(--border)',
        input:  'var(--surface)',
        ring:   'var(--accent)',
      },
      // Shape language is strictly rectilinear: every radius resolves to 0
      // so existing rounded-* classes flatten without per-file edits.
      borderRadius: {
        none: '0px',
        sm: '0px',
        DEFAULT: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        '3xl': '0px',
        full: '0px',
      },
      fontFamily: {
        sans:    ['"Hanken Grotesk"', 'sans-serif'],
        body:    ['"Hanken Grotesk"', 'sans-serif'],
        display: ['"Space Grotesk"', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'monospace'],
      },
      // Depth is tonal, never blurred.
      boxShadow: {
        sm: 'none',
        DEFAULT: 'none',
        md: 'none',
        lg: 'none',
        xl: 'none',
        '2xl': 'none',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
      fontSize: {
        '2xs': ['11px', '16px'],
        xs:    ['12px', '18px'],
        sm:    ['13px', '20px'],
        base:  ['14px', '22px'],
        md:    ['14px', '22px'],
        lg:    ['16px', '24px'],
        xl:    ['18px', '28px'],
        '2xl': ['20px', '28px'],
        '3xl': ['24px', '32px'],
        '4xl': ['30px', '36px'],
        // Blueprint type scale (DESIGN.md)
        'display-lg':         ['64px', { lineHeight: '1.1', letterSpacing: '-0.04em', fontWeight: '700' }],
        'headline-lg':        ['32px', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '600' }],
        'headline-lg-mobile': ['28px', { lineHeight: '1.2', fontWeight: '600' }],
        'headline-md':        ['24px', { lineHeight: '1.3', fontWeight: '500' }],
        'body-lg':            ['18px', { lineHeight: '1.6', fontWeight: '400' }],
        'body-md':            ['16px', { lineHeight: '1.6', fontWeight: '400' }],
        'label-sm':           ['12px', { lineHeight: '1.4', fontWeight: '500' }],
      },
    },
  },
  plugins: [],
}
