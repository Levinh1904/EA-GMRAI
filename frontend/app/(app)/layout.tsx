'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { AppShell } from '@/components/AppShell';
import { Loading } from '@/components/ui/ui';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace('/login');
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center' }}>
        <div style={{ margin: '0 auto' }}>
          <Loading label="Đang xác thực phiên đăng nhập…" />
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
