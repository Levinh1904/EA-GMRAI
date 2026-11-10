'use client';

import { useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Badge, Card, ErrorState, Loading, Notice, Segmented } from '@/components/ui/ui';
import { fmtNum } from '@/lib/format';
import { regimeColor, regimeLabel } from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type { OutcomeStats } from '@/lib/types';
import styles from '../../pages.module.css';

const HBars = dynamic(() => import('@/components/charts/HistoryCharts').then((m) => m.HBars), {
  ssr: false,
  loading: () => <Loading label="Đang tải biểu đồ…" />,
});

const AI_ORDER = ['TREND_UP', 'TREND_DOWN', 'SIDEWAYS', 'EARLY_TREND_UP', 'EARLY_TREND_DOWN'];
const REF_ORDER = ['TREND_UP', 'TREND_DOWN', 'SIDEWAYS', 'TRANSITION', 'HIGH_VOLATILITY', 'UNKNOWN'];

interface Row {
  key: string;
  prefix: 'AI' | 'Reference';
  regime: string;
  n: number;
  winRate: number | null;
  fwdReturn: number | null;
  mfe: number | null;
  mae: number | null;
  pctUp: number | null;
  pctDown: number | null;
  pctFlat: number | null;
  pctInRange: number | null;
}

function pct(v: number | null | undefined, digits = 1): string {
  return v == null || Number.isNaN(v) ? '—' : `${fmtNum(v, digits)}%`;
}

function num(v: number | null | undefined, digits = 2): string {
  return v == null || Number.isNaN(v) ? '—' : fmtNum(v, digits);
}

export default function OutcomesTab({ runId }: { runId: number }) {
  const { data, error, isLoading } = useApi<OutcomeStats>(`/history/runs/${runId}/stats/outcomes`);

  const horizons = useMemo(() => (data?.horizons?.length ? data.horizons : [12, 48, 96]), [data]);
  const [horizon, setHorizon] = useState<number>(0);

  const activeHorizon = useMemo(() => {
    if (horizons.includes(horizon)) return horizon;
    return horizons[0] ?? 12;
  }, [horizon, horizons]);

  const rows = useMemo<Row[]>(() => {
    const pr = data?.per_regime ?? {};
    const hKey = String(activeHorizon);
    const order = [...AI_ORDER.map((r) => `ai_regime:${r}`), ...REF_ORDER.map((r) => `reference_regime:${r}`)];
    const known = new Set(Object.keys(pr));
    const keys = [
      ...order.filter((k) => known.has(k)),
      ...[...known].sort().filter((k) => !order.includes(k)),
    ];
    return keys.flatMap((key) => {
      const bucket = pr[key]?.[hKey];
      if (!bucket) return [];
      const [prefix, regime] = key.split(':');
      return [
        {
          key,
          prefix: (prefix === 'reference_regime' ? 'Reference' : 'AI') as Row['prefix'],
          regime,
          n: bucket.n,
          winRate: bucket.win_rate_pct,
          fwdReturn: bucket.mean_fwd_return,
          mfe: bucket.mean_mfe,
          mae: bucket.mean_mae,
          pctUp: bucket.pct_up,
          pctDown: bucket.pct_down,
          pctFlat: bucket.pct_flat,
          pctInRange: bucket.pct_in_range,
        },
      ];
    });
  }, [data, activeHorizon]);

  if (isLoading) return <Loading label="Đang tải kết quả tương lai…" />;
  if (error) return <ErrorState error={error} />;
  if (!data) return <ErrorState title="Không có dữ liệu" error="Không nhận được kết quả stats/outcomes." />;

  const winBarData = rows.map((r) => ({
    label: `${r.prefix === 'AI' ? 'AI' : 'Ref'} · ${regimeLabel(r.regime)}`,
    value: r.winRate ?? 0,
    color:
      r.prefix === 'Reference'
        ? `${regimeColor(r.regime)}aa`
        : regimeColor(r.regime),
  }));

  return (
    <div className={styles.stack}>
      {data.note && (
        <Notice tone="info">
          <strong>Đánh giá chỉ để tham khảo:</strong> {data.note}
        </Notice>
      )}
      <Notice tone="info">
        Kết quả tương lai được tính tại thời điểm mỗi cây nến dự đoán và <b>không bao giờ</b> làm
        thay đổi dự đoán trong quá khứ — dữ liệu tương lai chỉ dùng để đánh giá hồi cứu. Win rate =
        % số lần lợi nhuận dương sau N nến M15 (12 nến ≈ 3 giờ, 48 nến ≈ 12 giờ, 96 nến ≈ 24 giờ).
      </Notice>

      <Card
        title={`Kết quả tương lai theo regime — run #${runId}`}
        subtitle={`Horizon ${activeHorizon} nến M15 (${fmtNum((activeHorizon * 15) / 60, 1)} giờ) · so sánh AI và Reference`}
        right={
          <Segmented
            options={horizons.map((h) => ({ value: String(h), label: `${h} nến` }))}
            value={String(activeHorizon)}
            onChange={(v) => setHorizon(Number(v))}
          />
        }
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nguồn</th>
                <th>Lớp</th>
                <th className="num">n</th>
                <th className="num">Win rate %</th>
                <th className="num">Fwd return TB</th>
                <th className="num">MFE TB</th>
                <th className="num">MAE TB</th>
                <th className="num">% tăng</th>
                <th className="num">% giảm</th>
                <th className="num">% đi ngang</th>
                <th className="num">% trong kênh</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td>
                    <Badge tone={r.prefix === 'AI' ? 'info' : 'neutral'}>{r.prefix}</Badge>
                  </td>
                  <td>
                    <Badge
                      tone="neutral"
                      style={{
                        color: regimeColor(r.regime),
                        background: `${regimeColor(r.regime)}1a`,
                        borderColor: `${regimeColor(r.regime)}55`,
                      }}
                    >
                      {regimeLabel(r.regime)}
                    </Badge>
                  </td>
                  <td className="num">{fmtNum(r.n, 0)}</td>
                  <td className="num">{pct(r.winRate)}</td>
                  <td className="num">{num(r.fwdReturn, 2)}</td>
                  <td className="num">{num(r.mfe, 2)}</td>
                  <td className="num">{num(r.mae, 2)}</td>
                  <td className="num">{pct(r.pctUp)}</td>
                  <td className="num">{pct(r.pctDown)}</td>
                  <td className="num">{pct(r.pctFlat)}</td>
                  <td className="num">{pct(r.pctInRange, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <div className={styles.muted} style={{ fontSize: 13, marginTop: 8 }}>
            Không có bucket nào cho horizon {activeHorizon}.
          </div>
        )}
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          MFE/MAE = biến động tối đa thuận lợi/bất lợi (USD) trong cửa sổ tương lai. % trong kênh =
          tỷ lệ nến đóng trong kênh Reference (giá tương lai nằm trong biên độ ±0.3 ATR so với giá
          dự đoán). Thống kê chỉ dùng để đánh giá hồi cứu — không phải tín hiệu giao dịch.
        </div>
      </Card>

      <Card
        title={`Win rate theo regime — horizon ${activeHorizon} nến`}
        subtitle="% số lần lợi nhuận dương sau N nến tương lai (AI so với Reference)"
      >
        <HBars
          horizontal
          height={Math.max(280, rows.length * 40 + 90)}
          fmt={(v) => `${fmtNum(v, 1)}%`}
          data={winBarData}
        />
        <div className={styles.muted} style={{ fontSize: 12, marginTop: 8 }}>
          Win rate gần 50% là kỳ vọng tự nhiên của chuyển động giá ngẫu nhiên — chênh lệch có ý nghĩa
          thống kê mới đáng chú ý. Chú giải: màu đậm = AI · màu nhạt = Reference.
        </div>
      </Card>
    </div>
  );
}
