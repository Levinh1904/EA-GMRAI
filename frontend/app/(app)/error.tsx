'use client';

// Route-level error boundary for the authenticated app. Without this, a render
// error dropped the user onto Next's bare default error page, outside the shell.

import Link from 'next/link';
import { useEffect } from 'react';

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('App render error:', error);
  }, [error]);

  return (
    <div
      style={{
        maxWidth: 680,
        margin: '80px auto',
        padding: '28px 32px',
        background: 'var(--surface-1, #131a24)',
        border: '1px solid var(--border, #222a38)',
        borderRadius: 12,
      }}
    >
      <h1 style={{ fontSize: 20, marginBottom: 8 }}>Đã xảy ra lỗi khi hiển thị trang</h1>
      <p style={{ color: 'var(--text-muted, #93a0b3)', fontSize: 13.5, lineHeight: 1.6 }}>
        Trang này không render được. Dữ liệu phía server không bị ảnh hưởng — bạn có thể thử lại
        hoặc chuyển sang trang khác.
      </p>

      <pre
        style={{
          marginTop: 16,
          padding: '10px 12px',
          background: 'var(--bg-elev, #0f1620)',
          borderRadius: 8,
          fontSize: 11.5,
          color: 'var(--status-danger, #ef4444)',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {error.message}
        {error.digest ? `\n\ndigest: ${error.digest}` : ''}
      </pre>

      <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
        <button
          type="button"
          onClick={reset}
          style={{
            padding: '8px 16px',
            borderRadius: 6,
            border: '1px solid var(--accent, #4c8dff)',
            background: 'var(--accent, #4c8dff)',
            color: '#fff',
            fontSize: 13,
            cursor: 'pointer',
          }}
        >
          Thử lại
        </button>
        <Link
          href="/"
          style={{
            padding: '8px 16px',
            borderRadius: 6,
            border: '1px solid var(--border, #222a38)',
            color: 'var(--text-primary, #e6edf7)',
            fontSize: 13,
            textDecoration: 'none',
          }}
        >
          Về Tổng quan
        </Link>
      </div>
    </div>
  );
}
