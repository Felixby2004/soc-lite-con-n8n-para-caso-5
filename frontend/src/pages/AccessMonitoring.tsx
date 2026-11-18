import { useCallback, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowUpRight, FlaskConical, ShieldAlert, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import { accessApi, type AccessEvent, type AccessPreview, type AccessReviewInput, type AccessSignal } from '@/api/access';
import { ConfirmDialog, Modal } from '@/components/Modal';
import { Pagination } from '@/components/Pagination';
import { EmptyState, ErrorState, Loading } from '@/components/States';
import { useToast } from '@/components/Toast';
import { usePermission } from '@/context/AuthContext';
import { getErrorMessage } from '@/utils/errors';
import { cx, formatDateTime } from '@/utils/format';
import { AccessIndicators } from './AccessIndicators';
import { AccessEvaluation } from './AccessEvaluation';
import { AccessModels } from './AccessModels';

const networkLabels = { direct: 'Directa', vpn: 'VPN', proxy: 'Proxy', unknown: 'Desconocida' };
const emptyFilters = { source: '', account: '', anomalies_only: false };
const demoSource = 'demo-vpn';
const reviewLabels = { expected: 'Esperado', anomalous: 'Anómalo' };
const severityLabels = { medium: 'Media', high: 'Alta', critical: 'Crítica' };

async function readBatchFile(file: File): Promise<unknown> {
  if (file.size > 1_000_000) throw new Error('El archivo debe pesar como máximo 1 MB.');
  try {
    return JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
  } catch {
    throw new Error('El archivo no contiene JSON válido.');
  }
}

function ScoreSignals({ signals }: { signals: AccessSignal[] }): JSX.Element {
  return signals.length ? (
    <ul className="divide-y divide-slate-800 rounded-md border border-slate-800">
      {signals.map((signal) => (
        <li key={signal.code} className="flex items-baseline gap-3 p-3 text-sm text-slate-300">
          <span className="shrink-0 font-mono font-semibold text-amber-300">+{signal.points}</span>
          {signal.detail}
        </li>
      ))}
    </ul>
  ) : <p className="text-sm text-slate-400">Las reglas disponibles no detectaron señales en este acceso.</p>;
}

function ReviewEditor({ event }: { event: AccessEvent }): JSX.Element {
  const canReview = usePermission('access:review');
  const client = useQueryClient();
  const toast = useToast();
  const [review, setReview] = useState(event.review);
  const [label, setLabel] = useState<AccessReviewInput['label'] | ''>(event.review?.label ?? '');
  const [note, setNote] = useState(event.review?.note ?? '');
  const save = useMutation({
    mutationFn: (input: AccessReviewInput) => accessApi.review(event.id, input),
    onSuccess: (saved) => {
      setReview(saved);
      void client.invalidateQueries({ queryKey: ['access', 'events'] });
      void client.invalidateQueries({ queryKey: ['access', 'evaluation'] });
      toast.success('Revisión guardada');
    },
  });
  return (
    <section className="mt-5 space-y-3 border-t border-slate-800 pt-4">
      <h3 className="font-semibold text-slate-100">Validación del analista</h3>
      <p className="text-sm text-slate-400">
        {review ? `${reviewLabels[review.label]} · ${formatDateTime(review.reviewed_at)}` : 'Pendiente de revisión'}
      </p>
      {canReview ? (
        <form className="space-y-3" onSubmit={(action) => { action.preventDefault(); if (label) save.mutate({ label, note }); }}>
          <p className="text-xs text-slate-400">Clasifica el acceso según la evidencia disponible. La etiqueta se usa para evaluar la detección.</p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-300">Etiqueta
              <select className="soc-input mt-1" required value={label}
                onChange={(change) => setLabel(change.target.value as AccessReviewInput['label'] | '')}>
                <option value="">Selecciona</option>
                <option value="expected">Esperado</option>
                <option value="anomalous">Anómalo</option>
              </select>
            </label>
            <label className="min-w-44 grow text-xs text-slate-300">Nota (opcional)
              <input className="soc-input mt-1" maxLength={300} value={note} onChange={(change) => setNote(change.target.value)} />
            </label>
            <button className="soc-btn-secondary" type="submit" disabled={!label || save.isPending}>
              {save.isPending ? 'Guardando…' : 'Guardar revisión'}
            </button>
          </div>
          {save.isError ? <p className="text-sm text-red-300" role="alert">{getErrorMessage(save.error)}</p> : null}
        </form>
      ) : review?.note ? <p className="break-words text-sm text-slate-300">{review.note}</p> : null}
    </section>
  );
}

function AccessEvidence({ event, onClose }: { event: AccessEvent; onClose: () => void }): JSX.Element {
  const canReadAlerts = usePermission('alerts:read');
  const profile = useQuery({
    queryKey: ['access', 'profile', event.source, event.account],
    queryFn: () => accessApi.profile(event),
  });
  return (
    <Modal open onClose={onClose} title={event.account} description={`${event.source} · ${formatDateTime(event.occurred_at)}`} size="lg">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        {[
          ['Puntaje', `${event.score}/100`],
          ['Acceso', event.outcome === 'success' ? 'Aceptado' : 'Fallido'],
          ['IP', event.source_ip ?? 'Sin dato'],
          ['Dispositivo', event.device_id ?? 'Sin dato'],
          ['Conexión', networkLabels[event.network]],
          ['ID de origen', event.event_id],
        ].map(([label, value]) => (
          <div className="min-w-0 rounded-md border border-slate-800 p-3" key={label}>
            <dt className="text-xs text-slate-400">{label}</dt>
            <dd className="mt-1 break-words text-slate-100">{value}</dd>
          </div>
        ))}
      </dl>
      <section className="mt-5 space-y-2">
        <h3 className="font-semibold text-slate-100">Evidencia del puntaje</h3>
        <p className="text-sm text-slate-400">Historial disponible al evaluar el acceso: {event.baseline_size} registros.</p>
        <ScoreSignals signals={event.signals} />
        {event.alert_id && canReadAlerts ? (
          <Link className="soc-btn-secondary mt-2 inline-flex" to={`/alerts/${event.alert_id}`}>
            Abrir alerta #{event.alert_id} <ArrowUpRight size={15} />
          </Link>
        ) : null}
      </section>
      <section className="mt-5 space-y-2 border-t border-slate-800 pt-4">
        <h3 className="font-semibold text-slate-100">Perfil actual de la cuenta</h3>
        {profile.isPending ? <p className="text-sm text-slate-400">Cargando perfil…</p> : null}
        {profile.isError ? (
          <p className="text-sm text-red-300" role="alert">No se pudo consultar el perfil. <button className="underline" type="button" onClick={() => void profile.refetch()}>Reintentar</button></p>
        ) : null}
        {profile.data ? (
          <dl className="space-y-2 text-sm text-slate-300">
            <div><dt className="inline font-medium">Historial</dt> <dd className="inline">{profile.data.samples} accesos en los últimos {profile.data.window_days} días.</dd></div>
            <div><dt className="inline font-medium">Horas observadas</dt> <dd className="inline">{profile.data.hours.map((hour) => `${String(hour).padStart(2, '0')}:00`).join(', ') || 'Sin historial'} ({profile.data.timezone})</dd></div>
            <div><dt className="inline font-medium">Dispositivos observados</dt> <dd className="inline break-all">{profile.data.devices.join(', ') || 'Sin datos'}</dd></div>
            {profile.data.samples < profile.data.minimum_samples ? (
              <div className="text-amber-300">El perfil necesita al menos {profile.data.minimum_samples} accesos para evaluar el patrón horario.</div>
            ) : null}
          </dl>
        ) : null}
      </section>
      {event.source !== demoSource ? <ReviewEditor event={event} /> : null}
    </Modal>
  );
}

export default function AccessMonitoring(): JSX.Element {
  const canImport = usePermission('access:write');
  const client = useQueryClient();
  const toast = useToast();
  const [section, setSection] = useState<'events' | 'evaluation' | 'models' | 'iocs'>('events');
  const [draft, setDraft] = useState(emptyFilters);
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AccessEvent | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [importError, setImportError] = useState('');
  const [preview, setPreview] = useState<AccessPreview | null>(null);
  const closeEvidence = useCallback(() => setSelected(null), []);
  const closeImport = useCallback(() => {
    setImportOpen(false);
    setFile(null);
    setImportError('');
    setPreview(null);
  }, []);
  const summary = useQuery({ queryKey: ['access', 'summary'], queryFn: accessApi.summary });
  const events = useQuery({
    queryKey: ['access', 'events', filters, page],
    queryFn: () => accessApi.events({ ...filters, page }),
    enabled: section === 'events',
  });
  const importer = useMutation({
    mutationFn: async (input: File) => accessApi.import(await readBatchFile(input)),
    onSuccess: (result) => {
      closeImport();
      applyFilters(emptyFilters);
      setSection('events');
      toast.success('Importación completada', `${result.imported} nuevos · ${result.skipped} repetidos · ${result.anomalies} anomalías.`);
      void client.invalidateQueries();
    },
    onError: (error) => setImportError(getErrorMessage(error)),
  });
  const previewer = useMutation({
    mutationFn: async (input: File) => accessApi.preview(await readBatchFile(input)),
    onSuccess: setPreview,
    onError: (error) => setImportError(getErrorMessage(error)),
  });
  const fileBusy = importer.isPending || previewer.isPending;
  const demo = useMutation({
    mutationFn: accessApi.demo,
    onSuccess: (result) => {
      setDemoOpen(false);
      applyFilters({ ...emptyFilters, source: demoSource });
      setSection('events');
      toast.success('Demostración disponible', `${result.imported} accesos nuevos · ${result.anomalies} anomalías nuevas.`);
      void client.invalidateQueries();
    },
    onError: (error) => {
      setDemoOpen(false);
      toast.error('No se pudo cargar la demostración', getErrorMessage(error));
    },
  });

  function applyFilters(next: typeof emptyFilters): void {
    setDraft(next);
    setFilters(next);
    setPage(1);
  }

  function submitFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    applyFilters({ ...draft, source: draft.source.trim(), account: draft.account.trim() });
  }

  const metrics = [
    ['Accesos registrados', summary.data?.events],
    ['Cuentas por origen', summary.data?.accounts],
    ['Anomalías detectadas', summary.data?.anomalies],
    ['Indicadores IP vigentes', summary.data?.active_iocs],
  ] as const;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-100">
            <ShieldAlert className="text-cyan-400" size={22} /> Monitoreo de accesos
          </h1>
          <p className="mt-1 text-sm text-slate-400">Investiga anomalías con el historial de cada cuenta y los indicadores IP vigentes.</p>
        </div>
        {canImport ? (
          <div className="flex flex-wrap gap-2">
            {summary.data?.demo_enabled ? (
              <button className="soc-btn-secondary" type="button" onClick={() => setDemoOpen(true)}><FlaskConical size={16} /> Cargar demostración</button>
            ) : null}
            <button className="soc-btn-primary" type="button" onClick={() => setImportOpen(true)}><Upload size={16} /> Importar JSON</button>
          </div>
        ) : null}
      </header>
      {summary.isError ? <ErrorState message={getErrorMessage(summary.error)} onRetry={() => void summary.refetch()} /> : null}
      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4" aria-label="Totales de todos los orígenes">
        {metrics.map(([label, value]) => (
          <article className="soc-panel p-4" key={label}>
            <h2 className="text-xs text-slate-400">{label}</h2>
            <p className="mt-2 font-mono text-2xl font-semibold text-slate-100">{value?.toLocaleString('es-PE') ?? '—'}</p>
          </article>
        ))}
      </section>
      <nav className="flex flex-wrap gap-x-5 gap-y-2 border-b border-slate-800" aria-label="Monitoreo de accesos">
        {([['events', 'Eventos y anomalías'], ['evaluation', 'Evaluación'], ['models', 'Modelos'], ['iocs', 'Indicadores IP']] as const).map(([value, label]) => (
          <button type="button" key={value} aria-pressed={section === value} onClick={() => setSection(value)}
            className={cx('border-b-2 px-1 pb-2 text-sm font-medium', section === value ? 'border-cyan-400 text-cyan-200' : 'border-transparent text-slate-400 hover:text-slate-200')}>
            {label}
          </button>
        ))}
      </nav>
      {section === 'iocs' ? <AccessIndicators /> : null}
      {section === 'evaluation' && summary.data ? <AccessEvaluation demoEnabled={summary.data.demo_enabled} /> : null}
      {section === 'models' && summary.data ? <AccessModels demoEnabled={summary.data.demo_enabled} /> : null}
      {section === 'events' ? (
        <section className="soc-panel">
          <form className="flex flex-wrap items-end gap-3 p-4" onSubmit={submitFilters}>
            <label className="block text-xs text-slate-300">Origen
              <input className="soc-input mt-1" placeholder="Todos" value={draft.source} maxLength={64} pattern="[a-z0-9][a-z0-9_.\-]{0,63}"
                onChange={(event) => setDraft({ ...draft, source: event.target.value })} />
            </label>
            <label className="block text-xs text-slate-300">Cuenta
              <input className="soc-input mt-1" placeholder="Cuenta exacta" value={draft.account} maxLength={160}
                onChange={(event) => setDraft({ ...draft, account: event.target.value })} />
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-300">
              <input type="checkbox" className="accent-cyan-400" checked={draft.anomalies_only}
                onChange={(event) => {
                  const anomalies_only = event.target.checked;
                  setDraft({ ...draft, anomalies_only });
                  setFilters({ ...filters, anomalies_only });
                  setPage(1);
                }} />
              Solo anomalías
            </label>
            <button className="soc-btn-secondary" type="submit">Filtrar</button>
            {(filters.source || filters.account || filters.anomalies_only) ? (
              <button className="soc-btn-secondary" type="button" onClick={() => applyFilters(emptyFilters)}>Limpiar</button>
            ) : null}
          </form>
          {events.isPending ? <Loading label="Cargando accesos…" /> : null}
          {events.isError ? <ErrorState message={getErrorMessage(events.error)} onRetry={() => void events.refetch()} /> : null}
          {events.data && (events.data.items.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-y border-slate-800 bg-slate-950/40 text-xs text-slate-400">
                  <tr>{['Fecha', 'Cuenta y origen', 'IP', 'Resultado', 'Puntaje', 'Revisión', 'Detalle'].map((label) => <th scope="col" className="px-4 py-3" key={label}>{label}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {events.data.items.map((row) => (
                    <tr key={row.id} className="hover:bg-slate-800/40">
                      <td className="whitespace-nowrap px-4 py-3">{formatDateTime(row.occurred_at)}</td>
                      <td className="min-w-40 max-w-64 px-4 py-3">
                        <span className="block break-all font-medium text-slate-100">{row.account}</span>
                        <span className="text-xs text-slate-400">{row.source === demoSource ? 'Simulado · demo-vpn' : row.source}</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{row.source_ip ?? '—'}</td>
                      <td className="px-4 py-3">{row.outcome === 'success' ? 'Aceptado' : 'Fallido'}</td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <span className={cx('font-mono font-semibold', row.is_anomaly ? 'text-amber-300' : 'text-slate-300')}>{row.score}/100</span>
                        {row.is_anomaly ? <span className="block text-xs text-amber-300">Anomalía</span> : null}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {row.source === demoSource ? 'Referencia simulada' : row.review ? reviewLabels[row.review.label] : 'Pendiente'}
                      </td>
                      <td className="px-4 py-3">
                        <button className="text-sm font-medium text-cyan-300 hover:underline" type="button" onClick={() => setSelected(row)}
                          aria-label={`Ver evidencia del evento ${row.event_id}`}>Ver evidencia</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState title="Sin accesos en esta vista" description="Importa un archivo o ajusta los filtros para consultar registros." />)}
          {events.data ? <Pagination page={page} pages={events.data.pages} onChange={setPage} /> : null}
        </section>
      ) : null}
      {selected ? <AccessEvidence key={selected.id} event={selected} onClose={closeEvidence} /> : null}
      <Modal open={importOpen} onClose={closeImport} preventClose={fileBusy} title="Importar o evaluar accesos"
        description="Adjunta un archivo JSON con un origen y hasta 250 eventos. El identificador de cada evento debe ser único en ese origen.">
        <form className="space-y-4" onSubmit={(event) => {
          event.preventDefault();
          setImportError('');
          if (file) importer.mutate(file);
        }}>
          <details className="text-sm text-slate-300">
            <summary className="cursor-pointer text-cyan-300">Ver ejemplo de formato</summary>
            <pre className="mt-2 overflow-x-auto rounded-md bg-slate-950 p-3 text-xs">{JSON.stringify({
              source: 'vpn-corporativa',
              events: [{ event_id: 'evt-001', account: 'usuario', occurred_at: new Date().toISOString(), outcome: 'success', source_ip: '192.0.2.10', device_id: 'portatil-01', network: 'vpn' }],
            }, null, 2)}</pre>
          </details>
          <label className="block text-sm text-slate-300">Archivo JSON
            <input className="soc-input mt-2" type="file" accept=".json,application/json" required disabled={fileBusy}
              onChange={(event) => { setFile(event.target.files?.[0] ?? null); setImportError(''); setPreview(null); }} />
          </label>
          {importError ? <p className="text-sm text-red-300" role="alert">{importError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <button className="soc-btn-primary" type="submit" disabled={!file || fileBusy}>{importer.isPending ? 'Importando…' : 'Importar accesos'}</button>
            <button className="soc-btn-secondary" type="button" disabled={!file || fileBusy}
              onClick={() => { setImportError(''); setPreview(null); if (file) previewer.mutate(file); }}>
              {previewer.isPending ? 'Evaluando…' : 'Evaluar un acceso sin guardar'}
            </button>
          </div>
          {preview ? (
            <section className="space-y-2 rounded-lg border border-cyan-900 bg-cyan-950/30 p-3" aria-live="polite">
              <h3 className="font-semibold text-cyan-100">
                Puntaje estimado {preview.score}/100 · {preview.severity ? `Severidad ${severityLabels[preview.severity]}` : 'Por debajo del umbral de alerta'}
              </h3>
              <p className="text-xs text-slate-400">Historial disponible al evaluar: {preview.baseline_size} registros.</p>
              <ScoreSignals signals={preview.signals} />
            </section>
          ) : null}
        </form>
      </Modal>
      <ConfirmDialog open={demoOpen} title="Cargar demostración" message="Se agregarán siete accesos simulados y sus alertas al origen demo-vpn."
        confirmLabel="Cargar demostración" loading={demo.isPending} onConfirm={() => demo.mutate()} onCancel={() => setDemoOpen(false)} />
    </div>
  );
}
