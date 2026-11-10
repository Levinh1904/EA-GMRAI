'use client';

// Self-contained panel: fetches history runs / training runs / backtests and
// renders the per-run performance-over-time chart.

import { ErrorState, Loading } from '@/components/ui/ui';
import { useApi } from '@/lib/swr';
import type {
  BacktestListResponse,
  HistoryRunListResponse,
  TrainingRunListResponse,
} from '@/lib/types';
import { ModelPerformanceChart } from './ModelPerformanceChart';

export function ModelPerformancePanel() {
  const history = useApi<HistoryRunListResponse>('/history/runs?limit=20', {
    revalidateOnFocus: false,
  });
  const training = useApi<TrainingRunListResponse>('/training/runs?limit=20', {
    revalidateOnFocus: false,
  });
  const backtests = useApi<BacktestListResponse>('/backtests?limit=20', {
    revalidateOnFocus: false,
  });

  if (history.isLoading || training.isLoading || backtests.isLoading) {
    return <Loading label="Đang tải chỉ số hiệu suất các run…" />;
  }
  if (history.error || training.error || backtests.error) {
    return (
      <ErrorState
        error={history.error ?? training.error ?? backtests.error}
        title="Không thể tải dữ liệu hiệu suất"
      />
    );
  }

  return (
    <ModelPerformanceChart
      historyRuns={history.data?.runs ?? []}
      trainingRuns={training.data?.runs ?? []}
      backtests={backtests.data?.runs ?? []}
    />
  );
}
