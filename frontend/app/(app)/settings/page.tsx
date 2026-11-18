'use client';

import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
  Stat,
  StatusPill,
} from '@/components/ui/ui';
import { API_BASE, getAuthToken } from '@/lib/api';
import { fmtNum, fmtUtcSec } from '@/lib/format';
import { statusTone } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import { ChangePasswordCard } from '@/components/account/ChangePasswordCard';
import type { SystemLogsResponse, SystemStatus } from '@/lib/types';
import styles from '../pages.module.css';

function logTone(level: string): 'info' | 'danger' | 'warning' | 'neutral' {
  switch (level.toUpperCase()) {
    case 'ERROR':
    case 'CRITICAL':
      return 'danger';
    case 'WARN':
    case 'WARNING':
      return 'warning';
    case 'INFO':
      return 'info';
    default:
      return 'neutral';
  }
}

export default function SettingsPage() {
  const { user, isAdmin, logout } = useAuth();
  const system = useApi<SystemStatus>('/system/status', { refreshInterval: 30000 });
  const logs = useApi<SystemLogsResponse>('/system/logs?limit=100', { refreshInterval: 30000 });

  return (
    <div className={styles.stack}>
      <PageHeader title="Cài đặt" subtitle="Trạng thái hệ thống, kết nối API và nhật ký" />

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card title="Kết nối API">
          <KV
            columns={1}
            items={[
              { label: 'Base URL', value: <span className="mono">{API_BASE}</span> },
              { label: 'Tiền tố endpoint', value: <span className="mono">/api/v1</span> },
              {
                label: 'Token đăng nhập',
                value: getAuthToken() ? (
                  <Badge tone="success">đã lưu (localStorage)</Badge>
                ) : (
                  <Badge tone="danger">không có</Badge>
                ),
              },
            ]}
          />
          <div style={{ marginTop: 12 }}>
            <Notice tone="info">
              Cấu hình qua biến môi trường <code>NEXT_PUBLIC_API_URL</code> (mặc định{' '}
              <code>http://localhost:8000</code>). Đổi biến này cần rebuild.
            </Notice>
          </div>
        </Card>

        <Card title="Tài khoản">
          {user && (
            <KV
              columns={1}
              items={[
                { label: 'Username', value: user.username },
                {
                  label: 'Role',
                  value: <Badge tone={isAdmin ? 'purple' : 'neutral'}>{user.role}</Badge>,
                },
                { label: 'User ID', value: user.id },
                {
                  label: 'is_active',
                  value: user.is_active ? <Badge tone="success">active</Badge> : <Badge tone="danger">inactive</Badge>,
                },
              ]}
            />
          )}
          <div style={{ marginTop: 12 }}>
            <Button variant="danger" onClick={logout}>
              Đăng xuất
            </Button>
          </div>
        </Card>
      </div>

      {user && <ChangePasswordCard username={user.username} />}

      <Card title="Trạng thái hệ thống" subtitle="/system/status">
        {system.isLoading && <Loading />}
        {system.error && <ErrorState error={system.error} />}
        {system.data && (
          <>
            <div className={`${styles.grid} ${styles.cols3}`} style={{ marginBottom: 14 }}>
              <Stat label="Tổng số nến" value={fmtNum(system.data.candles_total, 0)} />
              <Stat
                label="Mô hình hoạt động"
                value={system.data.active_models.length}
                sub={system.data.active_models.map((m) => m.model_type).join(', ')}
              />
              <Stat label="Job gần đây" value={system.data.recent_jobs.length} />
            </div>
            <div className={`${styles.grid} ${styles.cols2}`}>
              <div>
                <div className={styles.probTitle}>Active models</div>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Loại</th>
                        <th>Model ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {system.data.active_models.map((m, i) => (
                        <tr key={i}>
                          <td className="mono">{m.id ?? '—'}</td>
                          <td>
                            <Badge tone="teal">{m.model_type ?? '—'}</Badge>
                          </td>
                          <td className="mono">{m.model_id ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <div className={styles.probTitle}>Recent jobs</div>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Loại</th>
                        <th>Trạng thái</th>
                        <th>Kết thúc (UTC)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {system.data.recent_jobs.map((j) => (
                        <tr key={j.id}>
                          <td className="mono">{j.id}</td>
                          <td className="mono">{j.job_type}</td>
                          <td>
                            <StatusPill status={j.status} />
                          </td>
                          <td className="mono">{fmtUtcSec(j.finished_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        )}
      </Card>

      <Card title="Nhật ký hệ thống" subtitle="/system/logs — 100 dòng gần nhất">
        {logs.isLoading && <Loading />}
        {logs.error && <ErrorState error={logs.error} />}
        {logs.data && logs.data.logs.length === 0 && <Notice tone="info">Chưa có log nào.</Notice>}
        {logs.data && logs.data.logs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Level</th>
                  <th>Component</th>
                  <th>Thông điệp</th>
                  <th>Thời gian (UTC)</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.logs.map((l) => (
                  <tr key={l.id}>
                    <td className="mono">{l.id}</td>
                    <td>
                      <Badge tone={logTone(l.level)}>{l.level}</Badge>
                    </td>
                    <td className="mono">{l.component}</td>
                    <td style={{ whiteSpace: 'normal' }}>{l.message}</td>
                    <td className="mono">{fmtUtcSec(l.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
