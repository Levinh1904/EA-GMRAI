'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useAuth } from './AuthProvider';
import { Icon } from './icons';
import { Badge, RegimeBadge } from './ui/ui';
import { useApi } from '@/lib/swr';
import { API_BASE } from '@/lib/api';
import { fmtAge, fmtPct, fmtUtc } from '@/lib/format';
import type { RegimeLatest } from '@/lib/types';
import styles from './shell.module.css';

interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: '/', label: 'Tổng quan', icon: 'overview' },
  { href: '/market', label: 'Thị trường trực tiếp', icon: 'market' },
  { href: '/regime', label: 'AI Regime', icon: 'regime' },
  { href: '/history', label: 'Lịch sử Regime', icon: 'history' },
  { href: '/training', label: 'Trung tâm huấn luyện', icon: 'training' },
  { href: '/backtesting', label: 'Backtesting', icon: 'backtest' },
  { href: '/compare', label: 'So sánh mô hình', icon: 'compare' },
  { href: '/models', label: 'Kho mô hình', icon: 'models' },
  { href: '/data', label: 'Trung tâm dữ liệu', icon: 'data' },
  { href: '/settings', label: 'Cài đặt', icon: 'settings' },
];

function isActive(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Sidebar({ pathname }: { pathname: string }) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.brandLogo}>GM</div>
        <div>
          <div className={styles.brandName}>GMRAI</div>
          <div className={styles.brandSub}>Gold Market Regime AI</div>
        </div>
      </div>
      <nav className={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`${styles.navItem} ${isActive(pathname, item.href) ? styles.navItemActive : ''}`}
          >
            <Icon name={item.icon} size={17} />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className={styles.sidebarFoot}>
        <div className={styles.sidebarFootRow}>
          <span className={styles.apiDot} />
          API: <span className={styles.mono}>{API_BASE}</span>
        </div>
        <div className={styles.sidebarFootRow}>XAUUSD · M15 · v1</div>
      </div>
    </aside>
  );
}

function TopBar({ pathname }: { pathname: string }) {
  const { user, logout } = useAuth();
  const { data, error, isLoading } = useApi<RegimeLatest>('/regime/latest', {
    refreshInterval: 30000,
    revalidateOnFocus: true,
  });

  const current = NAV_ITEMS.find((n) => isActive(pathname, n.href));

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeft}>
        <span className={styles.topbarPage}>{current?.label ?? 'GMRAI'}</span>
        <span className={styles.topbarPath}>{pathname}</span>
      </div>
      <div className={styles.topbarRight}>
        {isLoading && <span className={styles.apiStatusMuted}>Đang cập nhật chế độ…</span>}
        {error && !isLoading && (
          <Badge tone="danger" title={error instanceof Error ? error.message : 'Lỗi API'}>
            API lỗi
          </Badge>
        )}
        {data && !isLoading && (
          <>
            <RegimeBadge regime={data.regime} />
            <span className={styles.topbarConf} title="Độ tin cậy của mô hình">
              {fmtPct(data.confidence)}
            </span>
            <span className={styles.topbarTime} title={`Cập nhật ${fmtUtc(data.timestamp)}`}>
              {fmtUtc(data.timestamp)} · {fmtAge(data.data_age_minutes)}
            </span>
            <Badge tone={data.data_source === 'synthetic_demo' ? 'yellow' : 'teal'}>
              {data.data_source === 'synthetic_demo' ? 'DEMO' : data.data_source}
            </Badge>
          </>
        )}
        <div className={styles.userChip}>
          <span className={styles.userAvatar}>{user?.username?.charAt(0).toUpperCase() ?? '?'}</span>
          <span className={styles.userName}>{user?.username}</span>
          <Badge tone={user?.role === 'admin' ? 'purple' : 'neutral'}>{user?.role}</Badge>
        </div>
        <button type="button" className={styles.logoutBtn} onClick={logout} title="Đăng xuất">
          <Icon name="logout" size={16} />
        </button>
      </div>
    </header>
  );
}

function DemoBanner() {
  const { data } = useApi<RegimeLatest>('/regime/latest', {
    refreshInterval: 30000,
    revalidateOnFocus: true,
  });
  if (!data || data.data_source !== 'synthetic_demo') return null;
  return (
    <div className={styles.demoBanner} role="alert">
      <span className={styles.demoBannerTitle}>DEMO DATA — synthetic, not live market data</span>
      <span className={styles.demoBannerSub}>
        Dữ liệu tổng hợp mô phỏng. KHÔNG phải dữ liệu thị trường trực tiếp — chỉ dùng để kiểm thử
        hệ thống.
      </span>
    </div>
  );
}

function Footer() {
  const { data } = useApi<RegimeLatest>('/regime/latest', { refreshInterval: 60000 });
  const source = data?.data_source ?? '—';
  return (
    <footer className={styles.footer}>
      <div className={styles.footerMain}>
        GMRAI là công cụ nghiên cứu. Kết quả phân tích không phải lời khuyên đầu tư và không gửi
        lệnh giao dịch.
      </div>
      <div className={styles.footerMeta}>
        <span>
          Dữ liệu: <span className={styles.mono}>{source}</span>
        </span>
        <span>Múi giờ hiển thị: UTC</span>
        <span>
          API: <span className={styles.mono}>{API_BASE}</span>
        </span>
      </div>
    </footer>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className={styles.shell}>
      <Sidebar pathname={pathname} />
      <div className={styles.main}>
        <TopBar pathname={pathname} />
        <DemoBanner />
        <main className={styles.content}>{children}</main>
        <Footer />
      </div>
    </div>
  );
}
