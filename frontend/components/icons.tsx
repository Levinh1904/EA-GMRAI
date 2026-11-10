import type { ReactNode } from 'react';

const ICON_PATHS: Record<string, ReactNode> = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  market: (
    <>
      <line x1="7" y1="4" x2="7" y2="20" />
      <line x1="17" y1="4" x2="17" y2="20" />
      <rect x="5" y="9" width="4" height="7" />
      <rect x="15" y="6" width="4" height="10" />
    </>
  ),
  regime: <polyline points="3 13 7 13 9 6 13 18 16 9 21 12" />,
  history: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <polyline points="12 7 12 12 15.5 14" />
      <line x1="3" y1="4" x2="6" y2="4" />
      <line x1="18" y1="4" x2="21" y2="4" />
    </>
  ),
  training: (
    <>
      <line x1="4" y1="7" x2="20" y2="7" />
      <circle cx="9" cy="7" r="2.2" />
      <line x1="4" y1="17" x2="20" y2="17" />
      <circle cx="15" cy="17" r="2.2" />
    </>
  ),
  backtest: <polygon points="7 5 19 12 7 19" />,
  compare: (
    <>
      <rect x="4" y="12" width="5" height="8" />
      <rect x="15" y="4" width="5" height="16" />
      <line x1="3" y1="21" x2="21" y2="21" />
    </>
  ),
  models: (
    <>
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <path d="M12 12l8-4.5" />
      <path d="M12 12v9" />
    </>
  ),
  data: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="2.8" />
      <path d="M4.5 5.5v13c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8v-13" />
      <path d="M4.5 12c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </>
  ),
};

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name] ?? <circle cx="12" cy="12" r="6" />}
    </svg>
  );
}
