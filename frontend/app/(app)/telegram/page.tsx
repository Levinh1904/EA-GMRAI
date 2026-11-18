'use client';

// Telegram notifications + next-bar forecast — one page for the alerting story:
//   1. transport status (configured / enabled / delivery counts)
//   2. manual actions (send test, push the latest signal now)
//   3. the full message log with filters — the audit trail of every attempt
//   4. forecast accuracy measured from this database's own scored predictions
//
// Everything is read from the real API; nothing here is mocked or estimated.

import { useMemo, useState } from 'react';
import { useAuth } from '@/components/AuthProvider';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  Notice,
  PageHeader,
  RegimeBadge,
  Stat,
} from '@/components/ui/ui';
import { ApiError, api } from '@/lib/api';
import { fmtNum, fmtPrice, fmtUtc, fmtUtcWithLocal } from '@/lib/format';
import { regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type {
  ForecastDirection,
  ForecastHistoryResponse,
  ForecastNextResponse,
  TelegramMessagesResponse,
  TelegramStatus,
  TelegramStatusResponse,
} from '@/lib/types';
import styles from '../pages.module.css';

const STATUS_TONE: Record<TelegramStatus, 'success' | 'warning' | 'danger' | 'neutral'> = {
  sent: 'success',
  skipped: 'warning',
  failed: 'danger',
  pending: 'neutral',
};

const STATUS_LABEL: Record<TelegramStatus, string> = {
  sent: 'Đã gửi',
  skipped: 'Bỏ qua',
  failed: 'Lỗi',
  pending: 'Chờ',
};

const REASON_LABEL: Record<string, string> = {
  duplicate_direction: 'Trùng hướng — không gửi lại',
  already_logged_for_bar: 'Đã ghi cho nến này',
  telegram_disabled: 'Telegram đang tắt',
  not_configured: 'Chưa cấu hình bot',
  no_prediction: 'Chưa có tín hiệu',
  ok: 'OK',
};

function reasonText(reason: string | null): string {
  if (!reason) return '—';
  return REASON_LABEL[reason] ?? reason;
}

function DirBadge({ direction }: { direction: ForecastDirection | null }) {
  if (!direction) return <span className={styles.muted}>—</span>;
  const tone = direction === 'UP' ? 'success' : direction === 'DOWN' ? 'danger' : 'neutral';
  const label = direction === 'UP' ? '↑ Tăng' : direction === 'DOWN' ? '↓ Giảm' : '→ Đi ngang';
  return <Badge tone={tone}>{label}</Badge>;
}

export default function TelegramPage() {
  const { isAdmin } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  const status = useApi<TelegramStatusResponse>('/telegram/status', { refreshInterval: 15000 });
  const messages = useApi<TelegramMessagesResponse>(
    `/telegram/messages?limit=100${statusFilter ? `&status=${statusFilter}` : ''}`,
    { refreshInterval: 10000 }
  );
  const forecast = useApi<ForecastNextResponse>('/forecast/next', { refreshInterval: 30000 });
  const history = useApi<ForecastHistoryResponse>('/forecast/history?limit=50', {
    refreshInterval: 30000,
  });

  const stats = forecast.data?.stats;

  const filtered = useMemo(() => messages.data?.messages ?? [], [messages.data]);

  async function run(label: string, fn: () => Promise<unknown>) {
    if (busy) return;
    setBusy(label);
    setToast(null);
    try {
      await fn();
      await Promise.all([status.mutate(), messages.mutate()]);
      setToast({ tone: 'ok', text: `${label}: xong` });
    } catch (e) {
      setToast({
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
        title="Telegram & Dự đoán nến"
        subtitle="Thông báo tín hiệu qua Telegram (chống trùng) + dự đoán nến M15 kế tiếp"
        right={
          status.data && (
            <div className={styles.toolbar} style={{ marginBottom: 0 }}>
              <Badge tone={status.data.configured ? 'success' : 'danger'}>
                {status.data.configured ? 'Bot đã cấu hình' : 'Chưa cấu hình bot'}
              </Badge>
              <Badge tone={status.data.enabled ? 'success' : 'neutral'}>
                {status.data.enabled ? 'Đang bật' : 'Đang tắt'}
              </Badge>
            </div>
          )
        }
      />

      {toast && (
        <Notice tone={toast.tone === 'ok' ? 'info' : 'danger'}>{toast.text}</Notice>
      )}

      {!status.data?.configured && (
        <Notice tone="warn">
          Chưa cấu hình Telegram. Thêm vào <code>backend/.env</code> rồi khởi động lại backend:
          <br />
          <code>GMRAI_TELEGRAM_BOT_TOKEN=...</code> · <code>GMRAI_TELEGRAM_CHAT_ID=...</code> ·{' '}
          <code>GMRAI_TELEGRAM_ENABLED=true</code>
          <br />
          Tạo bot qua <code>@BotFather</code>, lấy <code>chat_id</code> bằng cách nhắn cho bot rồi mở{' '}
          <code>api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code>.
        </Notice>
      )}

      {status.isLoading && <Loading label="Đang tải trạng thái Telegram…" />}
      {status.error && <ErrorState error={status.error} onRetry={() => void status.mutate()} />}

      {status.data && (
        <>
          <div className={`${styles.grid} ${styles.cols4}`}>
            <Stat label="Tổng tin nhắn" value={fmtNum(status.data.counts.total, 0)} sub="trong CSDL" />
            <Stat
              label="Đã gửi"
              value={fmtNum(status.data.counts.sent, 0)}
              sub="giao được tới Telegram"
              tone="up"
            />
            <Stat
              label="Bỏ qua"
              value={fmtNum(status.data.counts.skipped, 0)}
              sub="trùng chế độ / trong cooldown"
              tone="warn"
            />
            <Stat
              label="Lỗi"
              value={fmtNum(status.data.counts.failed, 0)}
              sub="không gửi được"
              tone="down"
            />
          </div>

          {status.data.throttle && (
            <Card
              title="Chống trùng & giới hạn tần suất"
              subtitle={status.data.throttle.note}
            >
              <div className={`${styles.grid} ${styles.cols3}`}>
                <Stat
                  label="Tối đa 1 tin mỗi"
                  value={`${status.data.throttle.min_bar_minutes} phút`}
                  sub={`${status.data.throttle.min_bar_seconds}s — khớp nến M15 (MT5)`}
                />
                <Stat
                  label="Cooldown còn lại"
                  value={
                    status.data.throttle.cooldown_left_seconds != null
                      ? `${status.data.throttle.cooldown_left_seconds}s`
                      : '—'
                  }
                  sub={
                    status.data.throttle.cooldown_left_seconds
                      ? 'đang chặn gửi tin mới'
                      : 'sẵn sàng gửi tin tiếp theo'
                  }
                  tone={
                    status.data.throttle.cooldown_left_seconds ? 'warn' : 'up'
                  }
                />
                <Stat
                  label="Tin bị chặn (50 gần nhất)"
                  value={fmtNum(status.data.throttle.signals_suppressed_recent, 0)}
                  sub={`chu kỳ quét ${status.data.throttle.check_interval_seconds}s`}
                />
              </div>
              <div className={styles.muted} style={{ fontSize: 12, marginTop: 10 }}>
                Bot kiểm tra mỗi {status.data.throttle.check_interval_seconds}s nhưng chỉ gửi
                khi: (1) đã qua {status.data.throttle.min_bar_minutes} phút kể từ tin trước,
                và (2) chế độ <strong>khác</strong> lần trước. Chế độ lặp lại bị bỏ qua — kể cả
                ĐI NGANG.
              </div>
            </Card>
          )}
        </>
      )}

      {isAdmin && (
        <Card title="Thao tác" subtitle="chỉ admin">
          <div className={styles.toolbar} style={{ marginBottom: 0 }}>
            <Button
              onClick={() => void run('Gửi tin thử', () => api.sendTelegramTest())}
              disabled={busy != null || !status.data?.configured}
            >
              {busy === 'Gửi tin thử' ? 'Đang gửi…' : 'Gửi tin thử'}
            </Button>
            <Button
              variant="ghost"
              onClick={() =>
                void run('Đẩy tín hiệu', () =>
                  api.notifyTelegram({ includeForecast: true })
                )
              }
              disabled={busy != null}
            >
              {busy === 'Đẩy tín hiệu' ? 'Đang đẩy…' : 'Đẩy tín hiệu hiện tại'}
            </Button>
            <span className={styles.muted} style={{ fontSize: 12 }}>
              Tín hiệu trùng hướng với lần gửi trước sẽ được ghi log là “bỏ qua”, không gửi lại.
            </span>
          </div>
        </Card>
      )}

      {/* ---------------- Next-bar forecast ---------------- */}
      <Card
        title="Dự đoán nến M15 kế tiếp"
        subtitle={
          forecast.data
            ? `Dựa trên nến đóng ${fmtUtc(forecast.data.ts)} → mục tiêu ${fmtUtc(forecast.data.target_ts)}`
            : 'đang tải…'
        }
        right={
          stats && stats.accuracy != null ? (
            <Badge tone={stats.accuracy > 0.55 ? 'success' : stats.accuracy < 0.45 ? 'danger' : 'warning'}>
              Độ chính xác thực đo: {fmtNum(stats.accuracy * 100, 1)}%
            </Badge>
          ) : (
            <Badge tone="neutral">chưa đủ dữ liệu chấm điểm</Badge>
          )
        }
      >
        {forecast.isLoading && <Loading label="Đang tính dự đoán…" />}
        {forecast.error && (
          <ErrorState error={forecast.error} onRetry={() => void forecast.mutate()} />
        )}
        {forecast.data && (
          <>
            <div className={styles.bigBadgeWrap}>
              <div>
                <div className={styles.probTitle}>Hướng nến kế tiếp</div>
                <div style={{ fontSize: 26, fontWeight: 600, marginTop: 4 }}>
                  <DirBadge direction={forecast.data.direction} />
                </div>
              </div>
              <Stat
                label="P(tăng)"
                value={`${fmtNum(forecast.data.probability_up * 100, 1)}%`}
                sub={`P(giảm) = ${fmtNum((1 - forecast.data.probability_up) * 100, 1)}%`}
              />
              <Stat
                label="Độ tin cậy"
                value={`${fmtNum(forecast.data.confidence * 100, 1)}%`}
                sub={forecast.data.direction === 'FLAT' ? 'dưới ngưỡng → không gọi hướng' : 'khoảng cách khỏi 50%'}
              />
              <Stat
                label="Chế độ hiện tại"
                value={regimeLabel(forecast.data.regime)}
                sub={forecast.data.regime ?? '—'}
              />
            </div>
            {forecast.data.note && (
              <Notice tone="warn" >
                <strong>Đọc kỹ:</strong> {forecast.data.note}
                {stats && stats.scored > 0 && (
                  <>
                    {' '}
                    Thực đo trên {fmtNum(stats.scored, 0)} dự đoán đã chấm:{' '}
                    <strong>{fmtNum((stats.accuracy ?? 0) * 100, 1)}%</strong>.
                  </>
                )}
              </Notice>
            )}
          </>
        )}
      </Card>

      {history.data && history.data.forecasts.length > 0 && (
        <Card
          title="Lịch sử dự đoán nến"
          subtitle={`${fmtNum(history.data.total, 0)} dự đoán · 50 gần nhất · đối chiếu với nến thực tế`}
        >
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: 'auto' }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Nến dự đoán</th>
                  <th>Hướng dự đoán</th>
                  <th className="num">P(tăng)</th>
                  <th>Thực tế</th>
                  <th className="num">Giá đóng</th>
                  <th>Kết quả</th>
                </tr>
              </thead>
              <tbody>
                {history.data.forecasts.map((f) => (
                  <tr key={f.id}>
                    <td className="mono">{fmtUtc(f.ts)}</td>
                    <td>
                      <DirBadge direction={f.direction} />
                    </td>
                    <td className="num">{fmtNum(f.probability_up * 100, 1)}%</td>
                    <td>
                      {f.pending ? (
                        <span className={styles.muted}>chưa đóng nến</span>
                      ) : (
                        <DirBadge direction={f.actual_direction} />
                      )}
                    </td>
                    <td className="num">{fmtPrice(f.actual_close)}</td>
                    <td>
                      {f.pending ? (
                        <Badge tone="neutral">chờ</Badge>
                      ) : f.correct === null ? (
                        <Badge tone="neutral">không gọi hướng</Badge>
                      ) : f.correct ? (
                        <Badge tone="success">đúng</Badge>
                      ) : (
                        <Badge tone="danger">sai</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ---------------- Message log ---------------- */}
      <Card
        title="Lịch sử tin nhắn Telegram"
        subtitle={`${fmtNum(messages.data?.total ?? 0, 0)} bản ghi · mọi lần gửi, bỏ qua và lỗi đều được lưu`}
        right={
          <div className={styles.toolbar} style={{ marginBottom: 0 }}>
            {(['', 'sent', 'skipped', 'failed'] as const).map((s) => (
              <Button
                key={s || 'all'}
                size="sm"
                variant={statusFilter === s ? 'primary' : 'ghost'}
                onClick={() => setStatusFilter(s)}
              >
                {s === '' ? 'Tất cả' : STATUS_LABEL[s as TelegramStatus]}
              </Button>
            ))}
            <Button size="sm" variant="ghost" onClick={() => void messages.mutate()}>
              Tải lại
            </Button>
          </div>
        }
      >
        {messages.isLoading && filtered.length === 0 && <Loading label="Đang tải tin nhắn…" />}
        {messages.error && (
          <ErrorState error={messages.error} onRetry={() => void messages.mutate()} />
        )}
        {!messages.isLoading && filtered.length === 0 && (
          <EmptyState
            title="Chưa có tin nhắn nào"
            hint="Bật Telegram trong backend/.env và chờ chu kỳ quét tiếp theo, hoặc bấm “Đẩy tín hiệu hiện tại”."
          />
        )}
        {filtered.length > 0 && (
          <div className={styles.stack} style={{ gap: 10 }}>
            {filtered.map((m) => (
              <details
                key={m.id}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  background: 'var(--bg-elevated)',
                }}
              >
                <summary
                  style={{
                    cursor: 'pointer',
                    display: 'flex',
                    gap: 10,
                    alignItems: 'center',
                    flexWrap: 'wrap',
                  }}
                >
                  <Badge tone={STATUS_TONE[m.status]}>{STATUS_LABEL[m.status]}</Badge>
                  <span className="mono" style={{ fontSize: 12 }}>
                    #{m.id}
                  </span>
                  {m.signal && <RegimeBadge regime={m.signal} />}
                  {m.previous_signal && m.previous_signal !== m.signal && (
                    <span className={styles.muted} style={{ fontSize: 12 }}>
                      ← {regimeLabel(m.previous_signal)}
                    </span>
                  )}
                  <span className={styles.muted} style={{ fontSize: 12 }}>
                    {fmtUtcWithLocal(m.bar_ts ?? m.created_at)}
                  </span>
                  {m.price != null && (
                    <span className="mono" style={{ fontSize: 12 }}>
                      {fmtPrice(m.price)}
                    </span>
                  )}
                  <span className={styles.muted} style={{ fontSize: 12 }}>
                    {reasonText(m.reason)}
                  </span>
                  {m.message_id != null && (
                    <Badge tone="neutral">msg #{m.message_id}</Badge>
                  )}
                </summary>

                <pre
                  style={{
                    marginTop: 10,
                    whiteSpace: 'pre-wrap',
                    fontSize: 12.5,
                    lineHeight: 1.5,
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--mono)',
                  }}
                >
                  {m.text}
                </pre>

                <div className={styles.muted} style={{ fontSize: 11.5, marginTop: 6 }}>
                  Tạo lúc {fmtUtc(m.created_at)}
                  {m.sent_at ? ` · gửi lúc ${fmtUtc(m.sent_at)}` : ''}
                  {m.confidence != null ? ` · tin cậy ${fmtNum(m.confidence * 100, 1)}%` : ''}
                  {m.error ? ` · lỗi: ${m.error}` : ''}
                </div>
              </details>
            ))}
          </div>
        )}
      </Card>

      <div className={styles.muted} style={{ fontSize: 12 }}>
        Ghi chú trung thực: dự đoán nến kế tiếp được đo trên dữ liệu thật và hiện có AUC ≈ 0.52 —
        gần như ngẫu nhiên. Trang này hiển thị đúng con số thực đo từ CSDL, không phải con số lý
        thuyết. Tín hiệu chế độ (regime) đáng tin hơn dự đoán nến đơn lẻ.
      </div>
    </div>
  );
}
