import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { accessApi, type EvaluationCount, type EvaluationFilters } from '@/api/access';
import { ExportMenu } from '@/components/ExportMenu';
import { EmptyState, ErrorState, Loading } from '@/components/States';
import { usePermission } from '@/context/AuthContext';
import { getErrorMessage } from '@/utils/errors';

const percent = new Intl.NumberFormat('es-PE', { style: 'percent', maximumFractionDigits: 1 });

function CountBars({ rows, scale }: { rows: EvaluationCount[]; scale: number }): JSX.Element {
  return (
    <ul className="space-y-3">
      {rows.map(({ label, count }) => (
        <li className="space-y-1" key={label}>
          <div className="flex items-baseline justify-between gap-3 text-sm text-slate-300">
            <span>{label}</span><span className="font-mono text-slate-100">{count.toLocaleString('es-PE')}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-800" aria-hidden="true">
            <div className="h-full rounded-full bg-cyan-400" style={{ width: `${(count / scale) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function AccessEvaluation({ demoEnabled }: { demoEnabled: boolean }): JSX.Element {
  const canExport = usePermission('reports:export');
  const [filters, setFilters] = useState<EvaluationFilters>({
    scope: demoEnabled ? 'demo' : 'operation', days: 30, threshold: 50,
  });
  const [draftThreshold, setDraftThreshold] = useState(String(filters.threshold));
  const query = useQuery({
    queryKey: ['access', 'evaluation', filters],
    queryFn: () => accessApi.evaluation(filters),
  });
  const data = query.data;
  function applyThreshold(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFilters({ ...filters, threshold: Number(draftThreshold) });
  }

  return (
    <section className="space-y-4" aria-label="Evaluación de detección">
      <div className="soc-panel flex flex-wrap items-end justify-between gap-4 p-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={applyThreshold}>
          <label className="text-xs text-slate-300">Origen de evaluación
            <select className="soc-input mt-1" value={filters.scope}
              onChange={(event) => setFilters({ ...filters, scope: event.target.value as EvaluationFilters['scope'] })}>
              <option value="operation">Operación</option>
              {demoEnabled ? <option value="demo">Demostración simulada</option> : null}
            </select>
          </label>
          {filters.scope === 'operation' ? (
            <label className="text-xs text-slate-300">Período
              <select className="soc-input mt-1" value={filters.days}
                onChange={(event) => setFilters({ ...filters, days: Number(event.target.value) })}>
                {[7, 30, 90].map((days) => <option key={days} value={days}>Últimos {days} días</option>)}
              </select>
            </label>
          ) : null}
          <label className="w-28 text-xs text-slate-300">Umbral (1–100)
            <input className="soc-input mt-1" type="number" required min={1} max={100} step={1} value={draftThreshold}
              onChange={(event) => setDraftThreshold(event.target.value)} />
          </label>
          <button className="soc-btn-secondary" type="submit">Comparar umbral</button>
        </form>
        {canExport && data ? (
          <ExportMenu contextLabel="Evaluación del Caso 5" options={(['pdf', 'docx', 'xlsx'] as const).map((format) => ({
            format, onExport: () => accessApi.exportEvaluation(filters, format),
          }))} />
        ) : null}
      </div>
      {query.isPending ? <Loading label="Calculando evaluación…" /> : null}
      {query.isError ? <ErrorState message={getErrorMessage(query.error)} onRetry={() => void query.refetch()} /> : null}
      {data ? (
        <>
          <p className="text-sm text-slate-400">
            Umbral evaluado {data.threshold}/100 · Umbral operativo {data.live_threshold}/100.
            {data.scope === 'demo' ? ' Las etiquetas de referencia pertenecen a una muestra simulada.' : ' Las métricas se calculan sobre los accesos revisados.'}
          </p>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ['Accesos evaluados', data.events],
              ['Con etiqueta', data.reviewed],
              ['Marcados al umbral', data.flagged],
              ['Cobertura de revisión', data.events ? percent.format(data.reviewed / data.events) : 'Sin base'],
            ].map(([label, value]) => (
              <article className="soc-panel p-4" key={label}>
                <h3 className="text-xs text-slate-400">{label}</h3>
                <p className="mt-2 font-mono text-xl font-semibold text-slate-100">{value.toLocaleString('es-PE')}</p>
              </article>
            ))}
          </div>
          {!data.events ? (
            <EmptyState title="Sin accesos en el período" description="Carga la demostración o importa eventos para empezar la evaluación." />
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              <article className="soc-panel space-y-3 p-4">
                <h3 className="font-semibold text-slate-100">Distribución de puntajes</h3>
                <p className="text-xs text-slate-400">Cantidad de accesos por rango, incluidos los que esperan revisión.</p>
                <CountBars rows={data.score_bands} scale={Math.max(1, ...data.score_bands.map((row) => row.count))} />
              </article>
              <article className="soc-panel space-y-3 p-4">
                <h3 className="font-semibold text-slate-100">Cobertura de datos</h3>
                <p className="text-xs text-slate-400">Eventos con cada dato disponible, de un total de {data.events}.</p>
                <CountBars rows={data.data_quality} scale={data.events} />
              </article>
            </div>
          )}
          {data.reviewed ? (
            <article className="soc-panel space-y-4 p-4">
              <div>
                <h3 className="font-semibold text-slate-100">Matriz de confusión</h3>
                <p className="mt-1 text-xs text-slate-400">Compara la etiqueta de referencia con el resultado al umbral elegido.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-72 text-left text-sm text-slate-200">
                  <thead className="border-b border-slate-800 text-xs text-slate-400">
                    <tr><th className="p-2" scope="col">Referencia</th><th className="p-2" scope="col">Marcado</th><th className="p-2" scope="col">Sin marcar</th></tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-slate-800">
                      <th className="p-2 font-medium" scope="row">Anómalo</th><td className="p-2">{data.confusion.true_positive}</td><td className="p-2 text-amber-300">{data.confusion.false_negative}</td>
                    </tr>
                    <tr>
                      <th className="p-2 font-medium" scope="row">Esperado</th><td className="p-2 text-amber-300">{data.confusion.false_positive}</td><td className="p-2">{data.confusion.true_negative}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {([
                  ['Precisión', data.precision], ['Sensibilidad', data.recall],
                  ['Especificidad', data.specificity], ['F1', data.f1],
                ] as const).map(([label, value]) => (
                  <div key={label} className="rounded-md border border-slate-800 p-3">
                    <dt className="text-xs text-slate-400">{label}</dt>
                    <dd className="mt-1 font-mono text-base text-slate-100">{value === null ? 'Sin base' : percent.format(value)}</dd>
                  </div>
                ))}
              </dl>
            </article>
          ) : data.events ? (
            <p className="soc-panel p-4 text-sm text-slate-300">Abre la evidencia de un evento y registra su revisión para calcular las métricas de detección.</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
