import { buildParams, downloadBlob, http } from './client';

export interface AccessSignal {
  code: string;
  points: number;
  detail: string;
}

export interface AccessEvent {
  id: number;
  source: string;
  event_id: string;
  account: string;
  occurred_at: string;
  outcome: 'success' | 'failure';
  source_ip: string | null;
  device_id: string | null;
  network: 'direct' | 'vpn' | 'proxy' | 'unknown';
  score: number;
  signals: AccessSignal[];
  baseline_size: number;
  alert_id: number | null;
  is_anomaly: boolean;
  review: AccessReview | null;
}

export interface AccessReviewInput {
  label: 'expected' | 'anomalous';
  note: string | null;
}

export interface AccessReview extends AccessReviewInput {
  reviewed_at: string;
}

export interface AccessPreview {
  score: number;
  signals: AccessSignal[];
  baseline_size: number;
  severity: 'medium' | 'high' | 'critical' | null;
}

export interface EvaluationFilters {
  scope: 'operation' | 'demo';
  days: number;
  threshold: number;
}

export interface EvaluationCount {
  label: string;
  count: number;
}

export interface AccessEvaluationResult {
  scope: EvaluationFilters['scope'];
  from_at: string | null;
  to_at: string;
  threshold: number;
  live_threshold: number;
  events: number;
  flagged: number;
  reviewed: number;
  confusion: { true_positive: number; false_positive: number; false_negative: number; true_negative: number };
  precision: number | null;
  recall: number | null;
  specificity: number | null;
  f1: number | null;
  score_bands: EvaluationCount[];
  data_quality: EvaluationCount[];
}

export interface AccessProfile {
  samples: number;
  devices: string[];
  hours: number[];
  timezone: string;
  window_days: number;
  minimum_samples: number;
}

export interface AccessIndicator {
  id: number;
  ip_address: string;
  reference: string;
  expires_at: string;
  active: boolean;
}

interface AccessSummary {
  events: number;
  accounts: number;
  anomalies: number;
  active_iocs: number;
  demo_enabled: boolean;
}

interface ImportResult {
  imported: number;
  skipped: number;
  anomalies: number;
}

export const accessApi = {
  summary: () => http.get<AccessSummary>('/access/summary'),
  events: (filters: { source: string; account: string; anomalies_only: boolean; page: number }) =>
    http.getPage<AccessEvent>('/access/events', { params: buildParams(filters) }),
  profile: (event: AccessEvent) =>
    http.get<AccessProfile>('/access/profile', { params: { source: event.source, account: event.account } }),
  import: (data: unknown) => http.post<ImportResult>('/access/events/import', data, { skipErrorToast: true }),
  preview: (data: unknown) => http.post<AccessPreview>('/access/events/preview', data, { skipErrorToast: true }),
  review: (id: number, data: AccessReviewInput) =>
    http.put<AccessReview>(`/access/events/${id}/review`, data, { skipErrorToast: true }),
  evaluation: (filters: EvaluationFilters) =>
    http.get<AccessEvaluationResult>('/access/evaluation', { params: { ...filters } }),
  exportEvaluation: (filters: EvaluationFilters, format: 'pdf' | 'docx' | 'xlsx') =>
    downloadBlob('/access/evaluation/export', { ...filters, format }, `evaluacion-accesos.${format}`),
  demo: () => http.post<ImportResult>('/access/demo', {}, { skipErrorToast: true }),
  indicators: (page: number) => http.getPage<AccessIndicator>('/access/iocs', { params: { page } }),
  saveIndicator: (data: { ip_address: string; reference: string; ttl_days: number }) =>
    http.put<AccessIndicator>('/access/iocs', data, { skipErrorToast: true }),
  revokeIndicator: (id: number) => http.del<AccessIndicator>(`/access/iocs/${id}`, { skipErrorToast: true }),
};
