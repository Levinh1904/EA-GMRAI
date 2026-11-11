'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KV,
  Loading,
  Notice,
  PageHeader,
  ProbRow,
  RegimeBadge,
  Stat,
} from '@/components/ui/ui';
import { fetchModelArtifactJson } from '@/lib/api';
import { fmtAge, fmtNum, fmtPct, fmtUtc, variantName } from '@/lib/format';
import {
  isEarlyTrend,
  permissionLabel,
  permissionTone,
  reasonCodeLabel,
  regimeColor,
  regimeLabel,
} from '@/lib/regime';
import { useApi } from '@/lib/swr';
import type {
  HmmArtifact,
  ModelDetail,
  RegimeHistoryResponse,
  RegimeLatest,
  StateMapEvidence,
  VariantResult,
} from '@/lib/types';
import styles from '../pages.module.css';

const RegimeStripChart = dynamic(() => import('@/components/charts/RegimeStripChart'), {
  ssr: false,
});

function StateMappingTable({ mapping }: { mapping: Record<string, StateMapEvidence> }) {
  const rows = Object.entries(mapping);
  if (rows.length === 0) return <EmptyState title="Không có state mapping" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>State</th>
            <th>Chế độ ngữ nghĩa</th>
            <th>Lý do</th>
            <th className="num">n_obs</th>
            <th className="num">Occupancy</th>
            <th className="num">ADX (mean)</th>
            <th className="num">Duration (mean)</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([state, info]) => {
            const ev = info.evidence ?? {};
            const nObs = typeof ev.n_obs === 'number' ? ev.n_obs : null;
            const occ = typeof ev.occupancy === 'number' ? ev.occupancy : null;
            const adx = typeof ev.adx_mean === 'number' ? ev.adx_mean : null;
            const dur = typeof ev.duration_mean === 'number' ? ev.duration_mean : null;
            return (
              <tr key={state}>
                <td className="mono">{state}</td>
                <td>
                  <RegimeBadge regime={info.regime} />
                </td>
                <td className="mono" style={{ whiteSpace: 'normal', fontSize: 12 }}>
                  {info.reason ?? '—'}
                </td>
                <td className="num">{nObs != null ? fmtNum(nObs, 0) : '—'}</td>
                <td className="num">{occ != null ? fmtPct(occ, 1) : '—'}</td>
                <td className="num">{adx != null ? fmtNum(adx, 3) : '—'}</td>
                <td className="num">{dur != null ? fmtNum(dur, 1) : '—'}</td>
                <td>
                  {ev.evidence === 'ok' ? (
                    <Badge tone="success">ok</Badge>
                  ) : ev.evidence != null ? (
                    <Badge tone="warning">{String(ev.evidence)}</Badge>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TransitionMatrix({ transmat }: { transmat: number[][] }) {
  const n = transmat.length;
  return (
    <div className="table-wrap">
      <table className={`${styles.heatTable} table`}>
        <thead>
          <tr>
            <th></th>
            {Array.from({ length: n }, (_, i) => (
              <th key={i}>S{i}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {transmat.map((row, i) => (
            <tr key={i}>
              <th>S{i}</th>
              {row.map((v, j) => (
                <td
                  key={j}
                  style={{ background: `rgba(76, 141, 255, ${Math.min(0.75, v * 1.2)})` }}
                  title={`P(S${i} → S${j}) = ${v.toFixed(4)}`}
                >
                  {v.toFixed(3)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VariantResultsTable({ results }: { results: Record<string, VariantResult> }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Biến thể</th>
            <th className="num">Validation opt score</th>
            <th className="num">Test macro F1</th>
            <th className="num">Test accuracy</th>
            <th className="num">False trend rate</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(results).map(([variant, v]) => (
            <tr key={variant}>
              <td>{variantName(variant)}</td>
              <td className="num">{fmtNum(v.validation_opt_score, 4)}</td>
              <td className="num">{fmtNum(v.test_macro_f1, 4)}</td>
              <td className="num">{fmtNum(v.test_accuracy, 4)}</td>
              <td className="num">{fmtNum(v.false_trend_rate, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RegimePage() {
  const latest = useApi<RegimeLatest>('/regime/latest', {
    refreshInterval: 15000,
    revalidateOnFocus: true,
  });
  const history = useApi<RegimeHistoryResponse>('/regime/history?limit=500', {
    refreshInterval: 60000,
  });

  const modelVersion = latest.data?.model_version;
  const model = useApi<ModelDetail>(
    modelVersion != null ? `/models/${modelVersion}` : null,
    { refreshInterval: 120000 }
  );

  const [artifact, setArtifact] = useState<HmmArtifact | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  useEffect(() => {
    if (!model.data || model.data.model_type !== 'hmm') {
      setArtifact(null);
      setArtifactError(null);
      return;
    }
    let cancelled = false;
    fetchModelArtifactJson<HmmArtifact>(model.data.version_id)
      .then((a) => {
        if (!cancelled) {
          setArtifact(a);
          setArtifactError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setArtifact(null);
          setArtifactError(e instanceof Error ? e.message : 'Không thể tải artifact');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [model.data]);

  if (latest.isLoading) return <Loading label="Đang tải phân tích regime…" />;
  if (latest.error) return <ErrorState error={latest.error} />;
  if (!latest.data) return <ErrorState title="Không có tín hiệu regime" />;

  const regime = latest.data;
  const hmmProbs = Object.entries(regime.probabilities.hmm_semantic ?? {}).sort(
    (a, b) => b[1] - a[1]
  );
  const rfProbs = Object.entries(regime.probabilities.rf ?? {}).sort((a, b) => b[1] - a[1]);
  const engineParams = model.data?.metrics?.engine_params;
  const variantResults = model.data?.metrics?.variant_results;
  const chosen = model.data?.metrics?.chosen_variant;

  const historyPoints = (history.data?.history ?? []).map((h) => ({ ts: h.ts, regime: h.regime }));
  const recentHistory = [...(history.data?.history ?? [])].reverse().slice(0, 12);

  return (
    <div className={styles.stack}>
      <PageHeader
        title="AI Regime"
        subtitle={`Phân tích chế độ thị trường ${regime.symbol} ${regime.timeframe} — HMM + Random Forest`}
        right={
          <span className={styles.muted}>
            Tín hiệu lúc <span className="mono">{fmtUtc(regime.timestamp)}</span>
          </span>
        }
      />

      {isEarlyTrend(regime.regime) && (
        <Notice tone="warn">
          <strong>Cảnh báo tín hiệu sớm:</strong> chế độ {regimeLabel(regime.regime)} (
          {regime.regime}) cho thấy xu hướng mới hình thành nhưng chưa được xác nhận — độ rủi ro
          cao hơn bình thường.
        </Notice>
      )}

      <div className={`${styles.grid} ${styles.cols3}`}>
        <Card
          title="Chế độ hiện tại"
          subtitle={`model v${regime.model_version} · features ${regime.feature_version}`}
          className={styles.colsSpan2}
        >
          <div className={styles.bigBadgeWrap}>
            <RegimeBadge regime={regime.regime} large />
            <Stat label="Độ tin cậy" value={fmtPct(regime.confidence)} sub="confidence" />
            <Stat
              label="Tuổi dữ liệu"
              value={`${fmtNum(regime.data_age_minutes, 1)} phút`}
              sub={fmtAge(regime.data_age_minutes)}
            />
            <Stat
              label="Quyền"
              value={permissionLabel(regime.permission)}
              tone={permissionTone(regime.permission)}
              sub="đầu ra nghiên cứu"
            />
          </div>
          <div style={{ marginTop: 12 }}>
            <Notice tone="warn">
              <strong>Nghiên cứu — không phải lệnh giao dịch.</strong> Quyền{' '}
              {permissionLabel(regime.permission)} là kết quả phân tích của mô hình, không phải tín
              hiệu mua/bán và không gửi lệnh giao dịch.
            </Notice>
          </div>
          <hr className={styles.rule} />
          <KV
            items={[
              { label: 'Khung thời gian', value: regime.timeframe },
              { label: 'Dữ liệu lúc', value: fmtUtc(regime.data_timestamp) },
              { label: 'Tín hiệu hết hạn', value: fmtUtc(regime.expiry) },
              { label: 'Model version', value: `v${regime.model_version}` },
              { label: 'Feature version', value: regime.feature_version },
              { label: 'Nguồn dữ liệu', value: regime.data_source },
            ]}
          />
          {regime.reason_codes.length > 0 && (
            <div className={styles.chips} style={{ marginTop: 12 }}>
              <span className={styles.muted}>Lý do:</span>
              {regime.reason_codes.map((code) => (
                <Badge key={code} tone="warning" title={code}>
                  {reasonCodeLabel(code)}
                </Badge>
              ))}
            </div>
          )}
        </Card>

        <Card title="Xác suất mô hình" subtitle="posterior của HMM và RF">
          <div className={styles.probTitle}>HMM — hậu nghiệm ngữ nghĩa</div>
          {hmmProbs.map(([label, v]) => (
            <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
          ))}
          <div className={styles.probTitle} style={{ marginTop: 14 }}>
            Random Forest — xác suất lớp
          </div>
          {rfProbs.map(([label, v]) => (
            <ProbRow key={label} label={label} value={v} color={regimeColor(label)} />
          ))}
        </Card>
      </div>

      <div className={`${styles.grid} ${styles.cols2}`}>
        <Card
          title="Bộ tham số engine (HMM)"
          subtitle={model.data ? `model v${model.data.version} · ${model.data.model_type}` : 'đang tải…'}
          right={chosen ? <Badge tone="teal">chọn: {variantName(chosen)}</Badge> : undefined}
        >
          {model.isLoading && <Loading />}
          {model.error && <ErrorState error={model.error} />}
          {engineParams &&
            Object.entries(engineParams).length > 0 &&
            <KV
              items={Object.entries(engineParams).map(([k, v]) => ({
                label: k,
                value: typeof v === 'number' ? fmtNum(v, 4) : String(v),
              }))}
            />}
          {!model.isLoading && !model.error && (!engineParams || Object.keys(engineParams).length === 0) && (
            <EmptyState hint="Phiên bản model không cung cấp engine_params" />
          )}
        </Card>

        <Card
          title="Kết quả theo biến thể"
          subtitle="đánh giá validation/test của HMM-only, RF-only và kết hợp"
        >
          {model.isLoading && <Loading />}
          {variantResults && Object.keys(variantResults).length > 0 && (
            <VariantResultsTable results={variantResults} />
          )}
          {!model.isLoading && (!variantResults || Object.keys(variantResults).length === 0) && (
            <EmptyState hint="Không có variant_results cho phiên bản này" />
          )}
        </Card>
      </div>

      {/* State mapping from HMM artifact */}
      {model.data?.model_type === 'hmm' && (
        <Card
          title="Ánh xạ trạng thái HMM → chế độ ngữ nghĩa"
          subtitle="trích từ artifact model.json (state_mapping)"
        >
          {!artifact && !artifactError && <Loading label="Đang tải artifact model.json…" />}
          {artifactError && (
            <Notice tone="danger">Không thể đọc artifact: {artifactError}</Notice>
          )}
          {artifact?.state_mapping && <StateMappingTable mapping={artifact.state_mapping} />}
          {artifact && !artifact.state_mapping && (
            <EmptyState hint="Artifact không chứa state_mapping" />
          )}
        </Card>
      )}

      {/* Transition matrix */}
      {artifact?.params?.transmat && (
        <Card
          title="Ma trận chuyển trạng thái HMM (transmat)"
          subtitle={`${artifact.params.transmat.length} trạng thái · P(S_i → S_j), màu càng đậm = xác suất càng cao`}
        >
          <TransitionMatrix transmat={artifact.params.transmat} />
        </Card>
      )}

      <Card title="Lịch sử chế độ" subtitle="chuỗi thời gian regime (tăng dần theo thời gian)">
        {history.isLoading && <Loading label="Đang tải lịch sử…" />}
        {history.error && <ErrorState error={history.error} />}
        {historyPoints.length > 0 && (
          <>
            <div className={styles.chartBox}>
              <RegimeStripChart points={historyPoints} height={110} />
            </div>
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Thời gian (UTC)</th>
                    <th>Chế độ</th>
                    <th className="num">Độ tin cậy</th>
                    <th>Quyền</th>
                    <th>Model version</th>
                  </tr>
                </thead>
                <tbody>
                  {recentHistory.map((h, i) => (
                    <tr key={i}>
                      <td className="mono">{fmtUtc(h.ts)}</td>
                      <td>
                        <RegimeBadge regime={h.regime} />
                      </td>
                      <td className="num">{fmtPct(h.confidence)}</td>
                      <td>{permissionLabel(h.permission)}</td>
                      <td className="mono">v{h.model_version_id ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {!history.isLoading && !history.error && historyPoints.length === 0 && (
          <EmptyState title="Chưa có lịch sử regime" />
        )}
      </Card>
    </div>
  );
}
