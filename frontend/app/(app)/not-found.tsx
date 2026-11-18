'use client';

// 404 inside the authenticated shell (previously an unknown URL showed Next's
// bare default page with no navigation back into the app).

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function AppNotFound() {
  const pathname = usePathname();
  return (
    <div
      style={{
        maxWidth: 620,
        margin: '90px auto',
        padding: '28px 32px',
        background: 'var(--surface-1, #131a24)',
        border: '1px solid var(--border, #222a38)',
        borderRadius: 12,
      }}
    >
      <div style={{ fontSize: 40, fontWeight: 700, color: 'var(--accent, #4c8dff)' }}>404</div>
      <h1 style={{ fontSize: 19, margin: '6px 0 8px' }}>Không tìm thấy trang</h1>
      <p style={{ color: 'var(--text-muted, #93a0b3)', fontSize: 13.5 }}>
        Đường dẫn <code className="mono">{pathname}</code> không tồn tại trong GMRAI.
      </p>
      <div style={{ display: 'flex', gap: 10, marginTop: 20, flexWrap: 'wrap' }}>
        {[
          { href: '/', label: 'Tổng quan' },
          { href: '/market', label: 'Thị trường' },
          { href: '/history', label: 'Lịch sử tín hiệu' },
          { href: '/settings', label: 'Cài đặt' },
        ].map((l) => (
          <Link
            key={l.href}
            href={l.href}
            style={{
              padding: '7px 14px',
              borderRadius: 6,
              border: '1px solid var(--border, #222a38)',
              color: 'var(--text-primary, #e6edf7)',
              fontSize: 13,
              textDecoration: 'none',
            }}
          >
            {l.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
