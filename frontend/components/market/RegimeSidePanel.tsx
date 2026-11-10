'use client';

// Right-hand regime panel for the Live Market page: current AI regime,
// HMM posterior, RF probabilities, reference regime (from the latest done
// history run), H1 trend context, volatility (ATR ratio), early-trend warning
// and permission with a research disclaimer.

import { Card, ErrorState, Loading, Notice, ProbRow, RegimeBadge, Stat } from '@/components/ui/ui';
import { fmtAge, fmtNum, fmtPct, fmtUtc } from '@/lib/format';
import {
  isEarlyTrend,
  permissionLabel,
  permissionTone,
  reasonCodeLabel,
  regimeColor,
  regimeLabel,
} from '@/lib/regime';
import type { HistoryBar, MultiTfStatsResponse, RegimeLatest } from '@/lib/types';
import styles from './market.module.css';

export function RegimeSidePanel({
  regime,
  regimeError,
  regimeLoading,
  lastBar,
  multiTf,
}: {
  regime: RegimeLatest | null;
  regimeError: unknown;
  regimeLoading: boolean;
  lastBar: HistoryBar | null;
  multiTf: MultiTfStatsResponse | null;
}) {
  if (regimeLoading && !regime) return <Loading label="Đang tải chế độ AI…" />;
  if (regimeError && !regime) return <ErrorState error={regimeError} title="Không thể tải chế độ AI" />;
  if (!regime) return <ErrorState title="Chưa có chế độ AI" />;

  const hmmProbs = Object.entries(regime.probabilities.hmm_semantic ?? {}).sort(
    (a, b) => b[1] - a[1]
  );
  const rfProbs = Object.entries(regime.probabilities.rf ?? {}).sort((a, b) => b[1] - a[1]);

  // H1 trend context from the latest history-run bar (or fall back to null).
  const h1 = lastBar?.h1_trend_context ?? null;
  const h1Thresh = multiTf?.thresholds?.h1_trend_context ?? 0.2;
  const h1Label =
    h1 == null ? '—' : h1 > h1Thresh ? 'Xu hướng tăng' : h1 < -h1Thresh ? 'Xu hướng giảm' : 'Trung lập';
  const h1Tone =
    h1 == null ? 'neutral' : h1 > h1Thresh ? 'up' : h1 < -h1Thresh ? 'down' : 'neutral';

  const atr = lastBar?.atr_ratio ?? null;

  return (
    <div className={styles.sidePanel}>
      <Card title="Chế độ AI hiện tại" subtitle={`Cập nhật ${fmtUtc(regime.timestamp)}`}>
        <div className={styles.regimeHead}>
          <RegimeBadge regime={regime.regime} large />
          <Stat label="Độ tin cậy" value={fmtPct(regime.confidence)} sub="confidence" />
        </div>
        <div className={styles.regimeMeta}>
          <div className={styles.regimeMetaRow}>
            <span>Dữ liệu lúc</span>
            <span className="num">{fmtUtc(regime.data_timestamp)}</span>
          </div>
          <div className={styles.regimeMetaRow}>
            <span>Tuổi dữ liệu</span>
            <span className="num">{fmtAge(regime.data_age_minutes)}</span>
          </div>
          <div className={styles.regimeMetaRow}>
            <span>Hết hạn</span>
            <span className="num">{fmtUtc(regime.expiry)}</span>
          </div>
          <div className={styles.regimeMetaRow}>
            <span>Model</span>
            <span className="num">v{regime.model_version} · {regime.feature_version}</span>
          </div>
          <div className={styles.regimeMetaRow}>
            <span>Nguồn</span>
            <span className="num">{regime.data_source}</span>
          </div>
          <div className={styles.regimeMetaRow}>
            <span>Quyền (nghiên cứu)</span>
            <span className={styles.permissionText} data-tone={permissionTone(regime.permission)}>
              {permissionLabel(regime.permission)}
            </span>
          </div>
        </div>
        {regime.reason_codes.length > 0 && (
          <div className={styles.reasonList}>
            {regime.reason_codes.map((code) => (
              <span key={code} className={styles.reasonChip} title={code}>
                {reasonCodeLabel(code)}
              </span>
            ))}
          </div>
        )}
      </Card>

      {isEarlyTrend(regime.regime) && (
        <Notice tone="warn">
          <strong>EARLY TREND ({regime.regime})</strong> — xu hướng mới chỉ ở giai đoạn sớm, chưa
          được xác nhận. Khả năng sai hướng cao hơn bình thường.
        </Notice>
      )}

      <Card title="Xác suất mô hình">
        <div className={styles.probSection}>
          <div className={styles.probTitle}>HMM — hậu nghiệm</div>
          {hmmProbs.map(([label, v]) => (
            <ProbRow key={label} label={regimeLabel(label)} value={v} color={regimeColor(label)} />
          ))}
        </div>
        <div className={styles.probSection}>
          <div className={styles.probTitle}>Random Forest</div>
          {rfProbs.map(([label, v]) => (
            <ProbRow key={label} label={regimeLabel(label)} value={v} color={regimeColor(label)} />
          ))}
        </div>
      </Card>

      <Card title="Bối cảnh thị trường" subtitle="Từ nến cuối của run lịch sử mới nhất">
        <div className={styles.ctxGrid}>
          <div className={styles.ctxItem}>
            <span className={styles.ctxLabel}>Reference regime</span>
            {lastBar?.reference_regime ? (
              <span style={{ color: regimeColor(lastBar.reference_regime), fontWeight: 600 }}>
                {regimeLabel(lastBar.reference_regime)}
              </span>
            ) : (
              <span className={styles.ctxMuted}>chưa có dữ liệu</span>
            )}
          </div>
          <div className={styles.ctxItem}>
            <span className={styles.ctxLabel}>Xu hướng H1</span>
            <span
              style={{
                color:
                  h1Tone === 'up' ? 'var(--status-ok)' : h1Tone === 'down' ? 'var(--status-danger)' : undefined,
                fontWeight: 600,
              }}
            >
              {h1Label}
              {h1 != null && <span className="num"> ({fmtNum(h1, 2)})</span>}
            </span>
          </div>
          <div className={styles.ctxItem}>
            <span className={styles.ctxLabel}>Biến động (ATR ratio)</span>
            {atr != null ? (
              <span className="num" title="Tỷ lệ ATR nến hiện tại so với trung bình">
                {fmtNum(atr, 2)}
                <span className={styles.ctxMuted}>
                  {' '}
                  {atr > 1 ? '· cao hơn trung bình' : '· dưới trung bình'}
                </span>
              </span>
            ) : (
              <span className={styles.ctxMuted}>—</span>
            )}
          </div>
          <div className={styles.ctxItem}>
            <span className={styles.ctxLabel}>Ngưỡng H1 context</span>
            <span className="num">±{fmtNum(h1Thresh, 2)} (từ stats/multi_tf)</span>
          </div>
        </div>
        {!lastBar && (
          <div className={styles.ctxMuted} style={{ marginTop: 8, fontSize: 11 }}>
            Các giá trị bối cảnh hiển thị sau khi tải dữ liệu run lịch sử.
          </div>
        )}
      </Card>

      <Notice tone="warn">
        <strong>Nghiên cứu — không phải lệnh giao dịch.</strong> Quyền{' '}
        {permissionLabel(regime.permission)} chỉ là đầu ra phân tích của mô hình, không cấu thành
        khuyến nghị mua/bán. GMRAI không gửi lệnh.
      </Notice>
    </div>
  );
}
