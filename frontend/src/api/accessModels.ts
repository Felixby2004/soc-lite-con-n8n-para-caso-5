import { downloadBlob, http } from './client';

export interface ModelConfiguration {
  scope: 'demo' | 'operation';
  algorithm: 'logistic' | 'tree';
  days: number;
  trials: number;
  seed: number;
}

export interface Partition {
  events: number;
  anomalous: number;
  expected: number;
  days: number;
  from_at: string | null;
  to_at: string | null;
}

export type Partitions = Record<'development' | 'validation' | 'test', Partition>;

export interface ModelDataset extends Partition {
  total_events: number;
  scope: ModelConfiguration['scope'];
  demo_version: string | null;
  partitions: Partitions | null;
  reason: string | null;
  features: { label: string; present: number }[];
}

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface RunSummary {
  id: number;
  created_at: string;
  status: RunStatus;
  configuration: ModelConfiguration;
}

type Parameters = Record<string, string | number | null>;

export interface ModelTrial {
  stage: 'outer' | 'final';
  fold: number;
  number: number;
  state: string;
  value: number | null;
  best: number;
  params: Parameters;
}

export interface ModelMetrics {
  roc_auc: number;
  average_precision: number;
  precision: number | null;
  recall: number | null;
  specificity: number | null;
  f1: number | null;
  accuracy: number;
  threshold: number;
  confusion: { true_positive: number; false_positive: number; false_negative: number; true_negative: number };
  roc: { x: number; y: number }[];
  pr: { x: number; y: number }[];
}

export interface ModelResult {
  dataset_sha256: string;
  partitions: Partitions;
  outer_folds: { fold: number; train: Partition; validation: Partition; average_precision: number; params: Parameters }[];
  mean_outer_ap: number;
  best_params: Parameters;
  best_inner_ap: number;
  model: ModelMetrics;
  heuristic: ModelMetrics;
  paired: { difference: number; days: number; interval: [number, number] | null; p_value: number | null; replicates: number };
  versions: { scikit_learn: string; optuna: string };
}

export interface RunDetail extends RunSummary {
  progress: { completed: number; total: number; trials: ModelTrial[] };
  result: ModelResult | null;
  error: string | null;
}

export interface Prediction {
  run_id: number;
  scope: ModelConfiguration['scope'];
  probability: number;
  threshold: number;
  flagged: boolean;
  severity: 'medium' | 'high' | 'critical' | null;
  heuristic: { score: number; baseline_size: number };
  contributions: { code: string; label: string; value: number; reference: number; delta: number }[];
}

const path = '/access/models';

export const accessModelsApi = {
  dataset: (scope: ModelConfiguration['scope'], days: number) =>
    http.get<ModelDataset>(`${path}/dataset`, { params: { scope, days }, skipErrorToast: true }),
  runs: () => http.get<RunSummary[]>(`${path}/runs`),
  run: (id: number) => http.get<RunDetail>(`${path}/runs/${id}`, { skipErrorToast: true }),
  start: (body: ModelConfiguration) => http.post<RunDetail>(`${path}/runs`, body, { skipErrorToast: true }),
  export: (id: number, format: 'pdf' | 'docx' | 'xlsx') =>
    downloadBlob(`${path}/runs/${id}/export`, { format }, `modelo-accesos-${id}.${format}`),
  predict: (id: number, input: unknown) =>
    http.post<Prediction>(`${path}/runs/${id}/predict`, input, { skipErrorToast: true }),
};
