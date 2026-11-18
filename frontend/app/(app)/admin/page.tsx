'use client';

// Admin: user accounts + collector API keys, on one page.
//
// Everything is read/written through the real API. Destructive actions
// (disable, revoke) ask for confirmation; the plaintext API key is shown once
// in a copyable block and never fetched again — matching the backend, which
// stores only a SHA-256 hash.

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Loading,
  Notice,
  PageHeader,
  PasswordField,
  Stat,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { fmtUtc } from '@/lib/format';
import { useApi } from '@/lib/swr';
import type { ApiKeyRow, ApiKeysResponse, UserListResponse, UserRow } from '@/lib/types';
import styles from '../pages.module.css';

const ROLES = ['admin', 'analyst', 'viewer'] as const;

function roleTone(role: string): 'purple' | 'teal' | 'neutral' {
  return role === 'admin' ? 'purple' : role === 'analyst' ? 'teal' : 'neutral';
}

export default function AdminPage() {
  const users = useApi<UserListResponse>('/users', { refreshInterval: 30000 });
  const keys = useApi<ApiKeysResponse>('/api-keys');

  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // new user form
  const [nu, setNu] = useState({ username: '', password: '', role: 'viewer' });
  // new key form
  const [nk, setNk] = useState({ name: '', role: 'ingest' });
  const [freshKey, setFreshKey] = useState<string | null>(null);

  async function act(label: string, fn: () => Promise<unknown>, after?: () => void) {
    if (busy) return;
    setBusy(label);
    setMsg(null);
    try {
      await fn();
      after?.();
      await Promise.all([users.mutate(), keys.mutate()]);
      setMsg({ tone: 'ok', text: `${label}: xong` });
    } catch (e) {
      setMsg({
        tone: 'err',
        text: e instanceof ApiError ? e.message : `${label} thất bại`,
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.stack}>
      <PageHeader
        title="Quản trị"
        subtitle="Tài khoản người dùng và API key cho collector — chỉ admin"
      />

      {msg && <Notice tone={msg.tone === 'ok' ? 'info' : 'danger'}>{msg.text}</Notice>}

      {users.isLoading && <Loading label="Đang tải người dùng…" />}
      {users.error && <ErrorState error={users.error} onRetry={() => void users.mutate()} />}

      {users.data && (
        <>
          <div className={`${styles.grid} ${styles.cols3}`}>
            <Stat label="Tổng người dùng" value={users.data.total} />
            <Stat
              label="Admin đang hoạt động"
              value={users.data.active_admins}
              sub="không thể hạ quyền admin cuối"
              tone={users.data.active_admins > 0 ? 'up' : 'down'}
            />
            <Stat
              label="API key đang hoạt động"
              value={(keys.data?.keys ?? []).filter((k) => k.is_active).length}
              sub={`${(keys.data?.keys ?? []).length} tổng cộng`}
            />
          </div>

          <Card title="Thêm người dùng" subtitle="mật khẩu tối thiểu 10 ký tự, có chữ và số">
            <form
              className={styles.formGrid}
              onSubmit={(e) => {
                e.preventDefault();
                void act(
                  'Tạo người dùng',
                  () => api.createUser(nu),
                  () => setNu({ username: '', password: '', role: 'viewer' })
                );
              }}
            >
              <Field label="Username">
                <input
                  value={nu.username}
                  onChange={(e) => setNu({ ...nu, username: e.target.value })}
                  placeholder="vd: analyst2"
                  autoComplete="off"
                />
              </Field>
              <PasswordField
                label="Mật khẩu"
                value={nu.password}
                onChange={(v) => setNu({ ...nu, password: v })}
                placeholder="≥10 ký tự, có chữ và số"
                hint={
                  nu.password.length > 0 && nu.password.length < 10
                    ? `Còn ${10 - nu.password.length} ký tự`
                    : undefined
                }
              />
              <Field label="Role">
                <select
                  value={nu.role}
                  onChange={(e) => setNu({ ...nu, role: e.target.value })}
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </Field>
              <div className={styles.formActions}>
                <Button
                  type="submit"
                  disabled={busy != null || nu.username.length < 3 || nu.password.length < 10}
                >
                  {busy === 'Tạo người dùng' ? 'Đang tạo…' : 'Tạo người dùng'}
                </Button>
              </div>
            </form>
          </Card>

          <Card title="Danh sách người dùng" subtitle={`${users.data.total} tài khoản`}>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Trạng thái</th>
                    <th>Tạo lúc</th>
                    <th>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {users.data.users.map((u: UserRow) => (
                    <tr key={u.id}>
                      <td className="num">{u.id}</td>
                      <td className="mono">{u.username}</td>
                      <td>
                        <Badge tone={roleTone(u.role)}>{u.role}</Badge>
                      </td>
                      <td>
                        {u.is_active ? (
                          <Badge tone="success">hoạt động</Badge>
                        ) : (
                          <Badge tone="danger">đã tắt</Badge>
                        )}
                      </td>
                      <td className="mono">{fmtUtc(u.created_at)}</td>
                      <td>
                        <div className={styles.btnRow}>
                          <select
                            value={u.role}
                            disabled={busy != null}
                            onChange={(e) =>
                              void act('Đổi role', () =>
                                api.updateUser(u.id, { role: e.target.value })
                              )
                            }
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                          <Button
                            size="sm"
                            variant={u.is_active ? 'ghost' : 'primary'}
                            disabled={busy != null}
                            onClick={() =>
                              void act(u.is_active ? 'Vô hiệu hoá' : 'Kích hoạt', () =>
                                api.updateUser(u.id, { is_active: !u.is_active })
                              )
                            }
                          >
                            {u.is_active ? 'Tắt' : 'Bật'}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={busy != null}
                            onClick={() => {
                              const pw = window.prompt(
                                `Mật khẩu mới cho ${u.username} (≥10 ký tự, có chữ và số):`
                              );
                              if (!pw) return;
                              void act('Đặt lại mật khẩu', () =>
                                api.adminResetPassword(u.id, pw)
                              );
                            }}
                          >
                            Đặt lại MK
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            disabled={busy != null}
                            title="Xoá hẳn khỏi database — không thể hoàn tác"
                            onClick={() => {
                              if (
                                !window.confirm(
                                  `Xoá HẲN tài khoản "${u.username}" khỏi database?\n\n` +
                                    'Không thể hoàn tác. Các bản ghi lịch sử (prediction, log) ' +
                                    'vẫn còn nhưng sẽ trỏ tới user id không tồn tại.\n\n' +
                                    'Nếu chỉ muốn chặn đăng nhập, dùng nút "Tắt".'
                                )
                              )
                                return;
                              void act('Xoá hẳn', () => api.purgeUser(u.id));
                            }}
                          >
                            Xoá
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card
            title="API key cho collector"
            subtitle="key chỉ hiển thị một lần khi tạo; hệ thống chỉ lưu hash SHA-256"
          >
            <form
              className={styles.formGrid}
              onSubmit={(e) => {
                e.preventDefault();
                void act(
                  'Tạo API key',
                  async () => {
                    const res = await api.createApiKey(nk);
                    setFreshKey(res.api_key);
                    setNk({ name: '', role: 'ingest' });
                  }
                );
              }}
            >
              <Field label="Tên key">
                <input
                  value={nk.name}
                  onChange={(e) => setNk({ ...nk, name: e.target.value })}
                  placeholder="vd: collector-vm2"
                />
              </Field>
              <Field label="Role">
                <select
                  value={nk.role}
                  onChange={(e) => setNk({ ...nk, role: e.target.value })}
                >
                  <option value="ingest">ingest</option>
                </select>
              </Field>
              <div className={styles.formActions}>
                <Button type="submit" disabled={busy != null || nk.name.length < 3}>
                  {busy === 'Tạo API key' ? 'Đang tạo…' : 'Tạo key'}
                </Button>
              </div>
            </form>

            {freshKey && (
              <Notice tone="warn">
                <strong>Key mới (chỉ hiện một lần):</strong>
                <div
                  className="mono"
                  style={{
                    marginTop: 8,
                    padding: '10px 12px',
                    background: 'var(--bg-elev)',
                    borderRadius: 6,
                    wordBreak: 'break-all',
                    userSelect: 'all',
                  }}
                >
                  {freshKey}
                </div>
                <div style={{ marginTop: 8 }}>
                  Copy ngay và dán vào <code>collector/.env</code> trên máy Windows, rồi khởi
                  động lại collector.
                </div>
                <div style={{ marginTop: 8 }}>
                  <Button size="sm" variant="ghost" onClick={() => setFreshKey(null)}>
                    Đã copy — ẩn đi
                  </Button>
                </div>
              </Notice>
            )}

            {keys.isLoading && <Loading label="Đang tải API key…" />}
            {keys.error && <ErrorState error={keys.error} onRetry={() => void keys.mutate()} />}
            {keys.data && keys.data.keys.length === 0 && (
              <EmptyState title="Chưa có API key nào" hint="Tạo key ở form phía trên." />
            )}
            {keys.data && keys.data.keys.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Tên</th>
                      <th>Role</th>
                      <th>Fingerprint</th>
                      <th>Dùng lần cuối</th>
                      <th>Trạng thái</th>
                      <th>Thao tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {keys.data.keys.map((k: ApiKeyRow) => (
                      <tr key={k.id}>
                        <td className="num">{k.id}</td>
                        <td className="mono">{k.name}</td>
                        <td>
                          <Badge tone="teal">{k.role}</Badge>
                        </td>
                        <td className="mono" style={{ fontSize: 11 }}>
                          {k.fingerprint}
                        </td>
                        <td className="mono">{k.last_used_at ? fmtUtc(k.last_used_at) : '—'}</td>
                        <td>
                          {k.is_active ? (
                            <Badge tone="success">hoạt động</Badge>
                          ) : (
                            <Badge tone="danger">đã thu hồi</Badge>
                          )}
                        </td>
                        <td>
                          <Button
                            size="sm"
                            variant={k.is_active ? 'ghost' : 'primary'}
                            disabled={busy != null}
                            onClick={() =>
                              void act(k.is_active ? 'Thu hồi' : 'Khôi phục', () =>
                                k.is_active
                                  ? api.revokeApiKey(k.id)
                                  : api.restoreApiKey(k.id)
                              )
                            }
                          >
                            {k.is_active ? 'Thu hồi' : 'Khôi phục'}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      <div className={styles.muted} style={{ fontSize: 12 }}>
        Mọi thay đổi tài khoản và API key đều được ghi vào nhật ký hệ thống
        (component <code>admin</code>) — xem ở trang Cài đặt.
      </div>
    </div>
  );
}
