import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Database, Download, ExternalLink, RefreshCw } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { datasetsApi, EVENT_LABELS, PUBLIC_SOURCE } from '@/api/datasets';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/components/Toast';
import { ErrorState } from '@/components/States';
import { formatDateTime, saveBlob } from '@/utils/format';
import { getErrorMessage } from '@/utils/errors';

export default function PublicDataset(): JSX.Element {
  const { hasPermission } = useAuth();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ['public-dataset'], queryFn: datasetsApi.summary });
  const importer = useMutation({
    mutationFn: datasetsApi.import,
    onSuccess: (result) => {
      toast.success('Importación completada', `${result.imported} nuevos; ${result.skipped} ya existentes.`);
      void client.invalidateQueries();
    },
    onError: (error) => toast.error('No se pudo importar', getErrorMessage(error)),
  });
  const exporter = useMutation({
    mutationFn: datasetsApi.export,
    onSuccess: (file) => saveBlob(file.blob, file.filename),
    onError: (error) => toast.error('No se pudo exportar', getErrorMessage(error)),
  });
  if (query.isPending) return <p className="text-slate-400">Cargando registros reales…</p>;
  if (query.isError) return <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} />;
  const data = query.data;
  const chart = data.event_types.map((item) => ({ ...item, label: EVENT_LABELS[item.name] ?? item.name }));
  const failureCount = data.event_types.find((item) => item.name === 'authentication_failed')?.count ?? 0;
  const acceptedCount = data.event_types.find((item) => item.name === 'authentication_accepted')?.count ?? 0;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-100"><Database className="text-cyan-400" size={22} />Datos reales de autenticación</h1>
          <p className="mt-1 text-sm text-slate-400">OpenSSH · Loghub · muestra pública de un servidor real de laboratorio</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {hasPermission('reports:export') && <button className="soc-btn" disabled={exporter.isPending || !data.imported_records} onClick={() => exporter.mutate()}><Download size={15} />Exportar datos reales</button>}
          {hasPermission('settings:write') && <button className="soc-btn-primary" disabled={importer.isPending} onClick={() => importer.mutate()}><RefreshCw size={15} />{importer.isPending ? 'Importando…' : 'Importar dataset'}</button>}
        </div>
      </header>
      <p className="rounded-lg border border-cyan-900 bg-cyan-950/30 p-4 text-sm leading-relaxed text-cyan-100">
        Este panel consulta exclusivamente registros reales importados en PostgreSQL. Los {data.other_records} registros de otras fuentes, incluida la demo, quedan fuera de sus métricas.
        El triaje IA del despliegue actual sigue en modo simulado. Los fallos de acceso observados no equivalen a ataques confirmados.
      </p>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicadores del dataset real">
        {[
          ['Registros reales importados', data.imported_records], ['IP de origen distintas', data.unique_ips],
          ['Registros de fallo', failureCount], ['Registros de acceso aceptado', acceptedCount],
        ].map(([label, value]) => <article key={label} className="soc-panel p-5"><h2 className="text-xs uppercase text-slate-400">{label}</h2><p className="mt-3 font-mono text-3xl text-cyan-300">{Number(value).toLocaleString('es-PE')}</p></article>)}
      </section>
      {!data.imported_records && <p className="text-amber-300">El archivo oficial está disponible. Un administrador debe importarlo para cargar sus 2.000 registros en la base de datos.</p>}
      <section className="grid gap-4 xl:grid-cols-2">
        <article className="soc-panel p-5">
          <h2 className="font-semibold text-slate-100">Eventos observados</h2><p className="mt-1 text-xs text-slate-400">Clasificación por contenido del log. Una sesión puede producir varios registros; no son intentos únicos ni ataques confirmados.</p>
          {chart.length > 0 && <ResponsiveContainer width="100%" height={300}><BarChart data={chart} layout="vertical" margin={{ left: 10, right: 20, top: 15 }}><CartesianGrid stroke="#1e293b" /><XAxis type="number" stroke="#94a3b8" allowDecimals={false} /><YAxis type="category" dataKey="label" width={155} stroke="#94a3b8" fontSize={11} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', color: '#e2e8f0' }} /><Bar dataKey="count" name="Registros" fill="#22d3ee" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>}
        </article>
        <article className="soc-panel p-5">
          <h2 className="font-semibold text-slate-100">IP con mayor número de registros</h2><p className="mt-1 text-xs text-slate-400">Frecuencia en la muestra; no es una lista de IP maliciosas.</p>
          {data.top_ips.length > 0 && <ResponsiveContainer width="100%" height={300}><BarChart data={data.top_ips} layout="vertical" margin={{ left: 5, right: 20, top: 15 }}><CartesianGrid stroke="#1e293b" /><XAxis type="number" stroke="#94a3b8" allowDecimals={false} /><YAxis type="category" dataKey="name" width={120} stroke="#94a3b8" fontSize={11} /><Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', color: '#e2e8f0' }} /><Bar dataKey="count" name="Registros" fill="#818cf8" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer>}
        </article>
      </section>
      <section className="soc-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold text-slate-100">Evidencias del archivo original</h2><Link className="text-sm text-cyan-400 hover:underline" to={`/alerts?source_name=${encodeURIComponent(PUBLIC_SOURCE)}`}>Ver todos los registros en Alertas →</Link></div>
        <p className="mt-1 text-xs text-slate-400">Primeras 20 líneas. La fecha original carece de año y zona horaria; las fechas del módulo Alertas corresponden a la importación.</p>
        <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-slate-400"><tr>{['Línea', 'Hora original', 'Tipo observado', 'Usuario', 'IP origen', 'Detalle'].map((label) => <th className="p-2" key={label}>{label}</th>)}</tr></thead><tbody>{data.sample.map((row) => <tr key={row.id} className="border-t border-slate-800"><td className="p-2 font-mono">{row.line}</td><td className="whitespace-nowrap p-2">{row.timestamp}</td><td className="p-2">{EVENT_LABELS[row.event_type]}</td><td className="p-2 font-mono">{row.username ?? 'No disponible'}</td><td className="p-2 font-mono">{row.source_ip ?? 'No disponible'}</td><td className="p-2"><Link className="text-cyan-400 hover:underline" to={`/alerts/${row.id}`}>Ver log #{row.id}</Link></td></tr>)}</tbody></table></div>
      </section>
      <section className="soc-panel space-y-3 p-5 text-sm text-slate-300">
        <h2 className="font-semibold text-slate-100">Procedencia y alcance</h2>
        <p>{data.manifest.sampling}</p><p>{data.manifest.timestamp_note}</p><p>{data.manifest.ground_truth} No se fabrican año, ubicación, IP de destino ni veredictos de compromiso.</p>
        <p><strong>Última importación:</strong> {data.last_import ? formatDateTime(data.last_import) : 'Pendiente'} · <strong>Nombres de usuario observados:</strong> {data.unique_users}</p>
        <p><strong>SHA-256 del archivo original:</strong> <span className="break-all font-mono text-xs">{data.manifest.sha256}</span></p>
        <p><strong>Versión de la fuente:</strong> <span className="break-all font-mono text-xs">{data.manifest.commit}</span> · {data.parser_version}</p>
        <p>{data.manifest.usage}</p><p>{data.manifest.citation}</p>
        <div className="flex flex-wrap gap-4 text-cyan-400"><a href={data.manifest.homepage} target="_blank" rel="noreferrer">Fuente oficial <ExternalLink className="inline" size={13} /></a><a href={data.manifest.download_url} target="_blank" rel="noreferrer">Archivo original</a><a href={data.manifest.citation_url} target="_blank" rel="noreferrer">Publicación científica</a></div>
      </section>
    </div>
  );
}
