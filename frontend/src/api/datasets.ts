import { http, downloadBlob } from './client';

export const PUBLIC_SOURCE = 'Loghub OpenSSH · registros reales';
export const EVENT_LABELS: Record<string, string> = {
  authentication_failed: 'Autenticación fallida', invalid_user: 'Usuario inválido',
  authentication_accepted: 'Autenticación aceptada', reverse_dns_warning: 'Advertencia DNS inverso',
  connection_closed: 'Conexión cerrada', other: 'Otros eventos',
};
export interface PublicDataset {
  manifest: {
    name: string; records: number; bytes: number; sha256: string; commit: string;
    homepage: string; download_url: string; sampling: string; timestamp_note: string;
    ground_truth: string; citation: string; citation_url: string; usage: string;
  };
  imported_records: number; other_records: number; unique_ips: number; unique_users: number;
  last_import: string | null; parser_version: string;
  event_types: Array<{ name: string; count: number }>;
  top_ips: Array<{ name: string; count: number }>;
  top_users: Array<{ name: string; count: number }>;
  original_days: Array<{ name: string; count: number }>;
  sample: Array<{ id: number; line: number; timestamp: string; event_type: string;
    username: string | null; source_ip: string | null; full_log: string }>;
}
export const datasetsApi = {
  summary: () => http.get<PublicDataset>('/datasets/loghub-openssh'),
  import: () => http.post<{ imported: number; skipped: number }>('/datasets/loghub-openssh/import'),
  export: () => downloadBlob('/datasets/loghub-openssh/export'),
};
