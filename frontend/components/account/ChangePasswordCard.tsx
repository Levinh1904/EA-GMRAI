'use client';

// Change-password form for the signed-in user.
//
// Security choices, deliberately visible in the UI:
//   * the CURRENT password is required — a stolen session token alone must not
//     let someone lock the real owner out
//   * the new password needs >= 10 chars, letters AND digits (mirrored by the
//     backend validator; the client check just fails faster)
//   * on success the API reissues an access token, stored immediately so the
//     session keeps working without a re-login

import { useState } from 'react';
import { Badge, Button, Card, Notice, PasswordField } from '@/components/ui/ui';
import { ApiError, api, setAuthToken } from '@/lib/api';
import styles from '@/app/(app)/pages.module.css';

const MIN_LEN = 10;

function strength(pw: string): { score: number; label: string; tone: string } {
  let s = 0;
  if (pw.length >= MIN_LEN) s += 1;
  if (pw.length >= 14) s += 1;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s += 1;
  if (/\d/.test(pw)) s += 1;
  if (/[^A-Za-z0-9]/.test(pw)) s += 1;
  if (s <= 2) return { score: s, label: 'Yếu', tone: 'var(--status-danger)' };
  if (s <= 3) return { score: s, label: 'Trung bình', tone: 'var(--status-warn)' };
  return { score: s, label: 'Mạnh', tone: 'var(--status-ok)' };
}

export function ChangePasswordCard({ username }: { username: string }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const s = strength(next);
  const localProblem =
    next.length > 0 && next.length < MIN_LEN
      ? `Mật khẩu mới cần ít nhất ${MIN_LEN} ký tự`
      : next.length > 0 && !(/[A-Za-z]/.test(next) && /\d/.test(next))
        ? 'Mật khẩu mới phải có cả chữ và số'
        : confirm.length > 0 && next !== confirm
          ? 'Mật khẩu xác nhận không khớp'
          : null;

  const canSubmit =
    !busy &&
    current.length > 0 &&
    next.length >= MIN_LEN &&
    next === confirm &&
    localProblem == null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const res = await api.changePassword({
        currentPassword: current,
        newPassword: next,
        confirmPassword: confirm,
      });
      if (res.access_token) setAuthToken(res.access_token);
      setCurrent('');
      setNext('');
      setConfirm('');
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Đổi mật khẩu thất bại. Vui lòng thử lại.'
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Đổi mật khẩu"
      subtitle={`tài khoản ${username}`}
      right={next.length > 0 ? <Badge tone="neutral">Độ mạnh: {s.label}</Badge> : undefined}
    >
      <form onSubmit={onSubmit} className={styles.formGrid}>
        <PasswordField
          label="Mật khẩu hiện tại"
          value={current}
          onChange={setCurrent}
          autoComplete="current-password"
        />

        <PasswordField
          label={`Mật khẩu mới (≥ ${MIN_LEN} ký tự, có chữ và số)`}
          value={next}
          onChange={setNext}
          hint={
            next.length > 0 ? (
              <span
                style={{
                  display: 'block',
                  height: 4,
                  borderRadius: 2,
                  background: 'var(--border)',
                  marginTop: 2,
                  overflow: 'hidden',
                }}
              >
                <span
                  style={{
                    display: 'block',
                    width: `${Math.min(100, (s.score / 5) * 100)}%`,
                    height: '100%',
                    background: s.tone,
                    transition: 'width 120ms ease',
                  }}
                />
              </span>
            ) : undefined
          }
        />

        <PasswordField label="Nhập lại mật khẩu mới" value={confirm} onChange={setConfirm} />

        {localProblem && <Notice tone="warn">{localProblem}</Notice>}
        {error && <Notice tone="danger">{error}</Notice>}
        {done && (
          <Notice tone="info">
            Đã đổi mật khẩu. Phiên đăng nhập hiện tại vẫn dùng được — lần đăng nhập
            sau hãy dùng mật khẩu mới.
          </Notice>
        )}

        <div className={styles.formActions}>
          <Button type="submit" disabled={!canSubmit}>
            {busy ? 'Đang cập nhật…' : 'Đổi mật khẩu'}
          </Button>
          <span className={styles.muted} style={{ fontSize: 12 }}>
            Cần mật khẩu hiện tại để xác nhận — tránh việc token bị lộ có thể chiếm tài khoản.
          </span>
        </div>
      </form>
    </Card>
  );
}
