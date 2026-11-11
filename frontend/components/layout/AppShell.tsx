'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import useSWR from 'swr';
import { useAuth } from '@/components/AuthProvider';
import { Icon } from '@/components/icons';
import { Badge, RegimeBadge } from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import { API_BASE } from '@/lib/api';
import { fmtAge, fmtPct, fmtUtc } from '@/lib/format';
import type { DashboardStats, RegimeLatest } from '@/lib/types';
import styles from './shell.module.css';

// ---------------------------------------------------------------------------
// Navigation model
// ---------------------------------------------------------------------------

interface NavItem {
  href: string;
  query?: string; // optional deep-link query, e.g. "tab=reference"
  label: string;
  icon: string;
}

type GroupStatus = 'ok' | 'warn' | 'danger' | 'offline' | 'loading';

interface NavGroup {
  key: string;
  label: string;
  items: NavItem[];
  statusKey: 'freshness' | 'health' | 'models' | 'sync';
}

const NAV_GROUPS: NavGroup[] = [
  {
    key: 'overview',
    label: 'Tổng quan',
    statusKey: 'freshness',
    items: [{ href: '/', label: 'Tổng quan', icon: 'overview' }],
  },
  {
    key: 'market',
    label: 'Thị trường',
    statusKey: 'freshness',
    items: [{ href: '/market', label: 'Thị trường trực tiếp', icon: 'market' }],
  },
  {
    key: 'ai',
    label: 'Phân tích AI',
    statusKey: 'health',
    items: [
      { href: '/regime', label: 'AI Regime', icon: 'regime' },
      { href: '/history', label: 'Lịch sử Regime', icon: 'history' },
      { href: '/history', query: 'tab=reference', label: 'So sánh Reference', icon: 'compare' },
      { href: '/replay', label: 'Replay lịch sử', icon: 'replay' },
    ],
  },
  {
    key: 'models',
    label: 'Mô hình',
    statusKey: 'models',
    items: [
      { href: '/training', label: 'Training', icon: 'training' },
      { href: '/backtesting', label: 'Backtesting', icon: 'backtest' },
      { href: '/models', label: 'Kho mô hình', icon: 'models' },
      { href: '/compare', label: 'So sánh mô hình', icon: 'compare' },
    ],
  },
  {
    key: 'system',
    label: 'Dữ liệu & Hệ thống',
    statusKey: 'sync',
    items: [
      { href: '/data', label: 'Trung tâm dữ liệu', icon: 'data' },
      { href: '/settings', label: 'Cài đặt', icon: 'settings' },
    ],
  },
];

const FLAT_ITEMS: Array<NavItem & { label: string }> = NAV_GROUPS.flatMap((g) => g.items);

function itemMatches(item: NavItem, pathname: string, search: string): boolean {
  if (item.href === '/') return pathname === '/';
  if (pathname !== item.href) return false;
  if (!item.query) return true;
  const params = new URLSearchParams(search);
  const [k, v] = item.query.split('=');
  return params.get(k) === v;
}

// ---------------------------------------------------------------------------
// Module status (real data only)
// ---------------------------------------------------------------------------

interface HealthResponse {
  api: string;
  database: string;
  worker: string;
}

const STATUS_META: Record<Exclude<GroupStatus, 'loading'>, { tone: string; title: string }> = {
  ok: { tone: 'var(--status-ok)', title: 'Hoạt động bình thường' },
  warn: { tone: 'var(--status-warn)', title: 'Có cảnh báo — kiểm tra chi tiết' },
  danger: { tone: 'var(--status-danger)', title: 'Có sự cố' },
  offline: { tone: 'var(--text-disabled)', title: 'Không lấy được trạng thái' },
};

function StatusDot({ status }: { status: GroupStatus }) {
  if (status === 'loading') return <span className={styles.statusDotPulse} />;
  const meta = STATUS_META[status];
  return (
    <span
      className={styles.statusDot}
      style={{ background: meta.tone }}
      title={meta.title}
      aria-label={meta.title}
    />
  );
}

function healthStatus(health: HealthResponse | null, error: unknown, loading: boolean): GroupStatus {
  if (loading) return 'loading';
  if (error || !health) return 'offline';
  if (health.api === 'ok' && health.database === 'ok' && health.worker === 'running') return 'ok';
  if (health.api === 'ok' && health.database === 'ok') return 'warn';
  return 'danger';
}

function freshnessStatus(dash: DashboardStats | null, error: unknown, loading: boolean): GroupStatus {
  if (loading) return 'loading';
  if (error || !dash) return 'offline';
  const tfs = Object.values(dash.data_freshness ?? {});
  if (tfs.some((f) => f.stale)) return 'danger';
  if (
    tfs.some(
      (f) => f.threshold_minutes != null && f.age_minutes > f.threshold_minutes * 0.66
    )
  )
    return 'warn';
  return 'ok';
}

function modelsStatus(dash: DashboardStats | null, error: unknown, loading: boolean): GroupStatus {
  if (loading) return 'loading';
  if (error || !dash) return 'offline';
  const count = (dash.active_models?.hmm?.length ?? 0) + (dash.active_models?.random_forest?.length ?? 0);
  return count > 0 ? 'ok' : 'warn';
}

function syncStatus(dash: DashboardStats | null, error: unknown, loading: boolean): GroupStatus {
  if (loading) return 'loading';
  if (error || !dash) return 'offline';
  const last = dash.last_sync?.[0];
  if (!last) return 'warn';
  return last.status === 'ok' ? 'ok' : last.status === 'failed' ? 'danger' : 'warn';
}

function statusTitleFor(key: NavGroup['statusKey'], status: GroupStatus, dash: DashboardStats | null): string {
  const base = STATUS_META[status as Exclude<GroupStatus, 'loading'>]?.title ?? '';
  if (status === 'ok') return base;
  if (!dash) return base;
  if (key === 'freshness') {
    const stale = Object.entries(dash.data_freshness ?? {})
      .filter(([, f]) => f.stale)
      .map(([tf]) => tf);
    return stale.length ? `Dữ liệu cũ: ${stale.join(', ')}` : base;
  }
  if (key === 'models') {
    return `Mô hình hoạt động: ${(dash.active_models?.hmm?.length ?? 0) + (dash.active_models?.random_forest?.length ?? 0)}`;
  }
  return base;
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const COLLAPSE_KEY = 'gmrai.sidebarCollapsed';

function Sidebar({
  pathname,
  search,
  collapsed,
  onToggleCollapse,
  showCollapse = true,
}: {
  pathname: string;
  search: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  showCollapse?: boolean;
}) {
  const dash = useApi<DashboardStats>('/stats/dashboard', {
    refreshInterval: 30000,
    revalidateOnFocus: false,
  });
  const health = useSWR<HealthResponse>(`${API_BASE}/api/v1/health`, (url: string) =>
    fetch(url, { headers: { Accept: 'application/json' } }).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json() as Promise<HealthResponse>;
    }), { refreshInterval: 30000, revalidateOnFocus: false }
  );

  const statuses = useMemo<Record<NavGroup['statusKey'], GroupStatus>>(
    () => ({
      freshness: freshnessStatus(dash.data ?? null, dash.error, dash.isLoading),
      health: healthStatus(health.data ?? null, health.error, health.isLoading),
      models: modelsStatus(dash.data ?? null, dash.error, dash.isLoading),
      sync: syncStatus(dash.data ?? null, dash.error, dash.isLoading),
    }),
    [dash.data, dash.error, dash.isLoading, health.data, health.error, health.isLoading]
  );

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.sidebarCollapsed : ''}`}>
      <div className={styles.brand}>
        <div className={styles.brandLogo}>GM</div>
        {!collapsed && (
          <div className={styles.brandText}>
            <div className={styles.brandName}>GMRAI</div>
            <div className={styles.brandSub}>Gold Market Regime AI</div>
          </div>
        )}
      </div>

      <nav className={styles.nav} aria-label="Điều hướng chính">
        {NAV_GROUPS.map((group) => {
          const status = statuses[group.statusKey];
          const title = statusTitleFor(group.statusKey, status, dash.data ?? null);
          return (
            <div key={group.key} className={styles.navGroup}>
              {collapsed ? (
                <div className={styles.navGroupDivider}>
                  <span className={styles.navGroupDividerLine} />
                  <StatusDot status={status} />
                </div>
              ) : (
                <div className={styles.navGroupLabel}>
                  <span>{group.label}</span>
                  <StatusDot status={status} />
                </div>
              )}
              {group.items.map((item) => {
                const active = itemMatches(item, pathname, search);
                const href = item.query ? `${item.href}?${item.query}` : item.href;
                return (
                  <Link
                    key={`${item.href}-${item.query ?? ''}`}
                    href={href}
                    className={`${styles.navItem} ${active ? styles.navItemActive : ''}`}
                    title={collapsed ? item.label : undefined}
                  >
                    <Icon name={item.icon} size={17} />
                    {!collapsed && <span>{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      <div className={styles.sidebarFoot}>
        {showCollapse && (
          <button
            type="button"
            className={styles.collapseBtn}
            onClick={onToggleCollapse}
            title={collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng'}
            aria-label={collapsed ? 'Mở rộng thanh điều hướng' : 'Thu gọn thanh điều hướng'}
          >
            <Icon name={collapsed ? 'chevronRight' : 'chevronLeft'} size={15} />
            {!collapsed && <span>Thu gọn</span>}
          </button>
        )}
        {!collapsed && (
          <>
            <div className={styles.sidebarFootRow}>
              <span className={styles.apiDot} />
              API: <span className={styles.mono}>{API_BASE}</span>
            </div>
            <div className={styles.sidebarFootRow}>XAUUSD · M15 · v1</div>
          </>
        )}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------

function TopBar({
  pathname,
  search,
  onOpenDrawer,
}: {
  pathname: string;
  search: string;
  onOpenDrawer: () => void;
}) {
  const { user, logout } = useAuth();
  const { data, error, isLoading } = useApi<RegimeLatest>('/regime/latest', {
    refreshInterval: 30000,
    revalidateOnFocus: true,
  });

  const current = FLAT_ITEMS.find((n) => itemMatches(n, pathname, search));

  return (
    <header className={styles.topbar}>
      <div className={styles.topbarLeft}>
        <button
          type="button"
          className={styles.menuBtn}
          onClick={onOpenDrawer}
          aria-label="Mở menu điều hướng"
        >
          <Icon name="menu" size={18} />
        </button>
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

// ---------------------------------------------------------------------------
// Banner / Footer
// ---------------------------------------------------------------------------

function DemoBanner() {
  const { data } = useApi<RegimeLatest>('/regime/latest', {
    refreshInterval: 30000,
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
  const { data } = useApi<RegimeLatest>('/regime/latest', { refreshInterval: 15000 });
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

// ---------------------------------------------------------------------------
// AppShell
// ---------------------------------------------------------------------------

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const search = searchParams?.toString() ?? '';
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const initialised = useRef(false);

  // Persist collapsed state in localStorage.
  useEffect(() => {
    if (initialised.current) return;
    initialised.current = true;
    try {
      const saved = window.localStorage.getItem(COLLAPSE_KEY);
      if (saved === '1' || saved === 'true') setCollapsed(true);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0');
      } catch {
        /* storage unavailable */
      }
      return next;
    });
  }, []);

  // Close the drawer on navigation and on Escape.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname, search]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  return (
    <div className={styles.shell}>
      <div className={styles.sidebarDesktop}>
        <Sidebar
          pathname={pathname}
          search={search}
          collapsed={collapsed}
          onToggleCollapse={toggleCollapse}
        />
      </div>

      {drawerOpen && (
        <div className={styles.drawerLayer}>
          <div className={styles.drawerBackdrop} onClick={() => setDrawerOpen(false)} />
          <div className={styles.drawer}>
            <div className={styles.drawerHead}>
              <span className={styles.drawerTitle}>Điều hướng</span>
              <button
                type="button"
                className={styles.drawerClose}
                onClick={() => setDrawerOpen(false)}
                aria-label="Đóng menu"
              >
                <Icon name="close" size={18} />
              </button>
            </div>
            <Sidebar
              pathname={pathname}
              search={search}
              collapsed={false}
              onToggleCollapse={() => undefined}
              showCollapse={false}
            />
          </div>
        </div>
      )}

      <div className={styles.main}>
        <TopBar
          pathname={pathname}
          search={search}
          onOpenDrawer={() => setDrawerOpen(true)}
        />
        <DemoBanner />
        <main className={styles.content}>{children}</main>
        <Footer />
      </div>
    </div>
  );
}
