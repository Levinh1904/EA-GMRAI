'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/AuthProvider';
import { ApiError } from '@/lib/api';
import styles from './login.module.css';

export default function LoginPage() {
  const { user, loading, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace('/');
  }, [loading, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      router.replace('/');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Sai tên đăng nhập hoặc mật khẩu.');
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Đăng nhập thất bại. Vui lòng thử lại.');
      }
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <div className={styles.logo}>GM</div>
          <div>
            <div className={styles.name}>GMRAI</div>
            <div className={styles.sub}>TRADE_ENS · XAUUSD</div>
          </div>
        </div>
        <h1 className={styles.title}>Đăng nhập</h1>
        <p className={styles.lead}>Nghiên cứu tín hiệu XAUUSD M15 bằng TRADE_ENS (LONG/SHORT/NO_TRADE).</p>
        <form onSubmit={onSubmit} className={styles.form}>
          <label className={styles.field}>
            <span className={styles.label}>Tên đăng nhập</span>
            <input
              className={styles.input}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
            />
          </label>
          <label className={styles.field}>
            <span className={styles.label}>Mật khẩu</span>
            <input
              className={styles.input}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error && <div className={styles.error}>{error}</div>}
          <button type="submit" className={styles.submit} disabled={submitting}>
            {submitting ? 'Đang đăng nhập…' : 'Đăng nhập'}
          </button>
        </form>
      </div>
      <div className={styles.disclaimer}>
        GMRAI là công cụ nghiên cứu. Kết quả phân tích không phải lời khuyên đầu tư và không gửi
        lệnh giao dịch.
      </div>
    </div>
  );
}
