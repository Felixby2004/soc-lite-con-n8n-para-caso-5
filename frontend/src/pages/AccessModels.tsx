import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { accessModelsApi, type ModelConfiguration, type ModelDataset, type RunDetail, type RunStatus } from '@/api/accessModels';
import { EmptyState, ErrorState, Loading } from '@/components/States';
import { usePermission } from '@/context/AuthContext';
import { getErrorMessage } from '@/utils/errors';
import { formatDateTime } from '@/utils/format';
import { AccessModelResults, PartitionTable, algorithmLabel, formatPercent, scopeLabel } from './AccessModelResults';

const statusLabel: Record<RunStatus, string> = {
  queued: 'En cola', running: 'Entrenando', completed: 'Completada', failed: 'Fallida',
};
const isActive = (status?: RunStatus): boolean => status === 'queued' || status === 'running';
const searchLabel = (fold: number): string => fold === 6 ? 'Búsqueda final' : `Pliegue externo ${fold}`;
const formatParams = (params: Record<string, string | number | null>): string => Object.entries(params)
  .map(([key, value]) => `${key} = ${typeof value === 'number' ? Number(value.toPrecision(4)) : value ?? 'sin ponderación'}`)
  .join(' · ');

function DatasetDetails({ dataset }: { dataset: ModelDataset }): JSX.Element {
  return (
    <div className="space-y-3 border-t border-slate-800 pt-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Eventos disponibles', dataset.total_events], ['Con etiqueta', dataset.events],
          ['Esperados', dataset.expected], ['Anómalos', dataset.anomalous],
        ].map(([label, value]) => (
          <div className="rounded-lg border border-slate-800 p-3" key={label}>
            <p className="text-xs text-slate-400">{label}</p>
            <p className="mt-1 font-mono text-lg text-slate-100">{value.toLocaleString('es-PE')}</p>
          </div>
        ))}
      </div>
      {dataset.reason ? <p className="rounded-lg border border-amber-900/70 bg-amber-950/30 p-3 text-sm text-amber-200">{dataset.reason}</p> : null}
      {dataset.partitions ? <PartitionTable data={dataset.partitions} /> : null}
      {dataset.events ? (
        <details className="rounded-lg border border-slate-800 p-3">
          <summary className="cursor-pointer text-sm text-slate-200">Distribución de atributos</summary>
          <p className="mt-2 text-xs text-slate-400">Eventos etiquetados donde el atributo está presente, activo o tiene valor mayor que cero.</p>
          <ul className="mt-3 grid gap-2 md:grid-cols-2">
            {dataset.features.map((feature) => (
              <li className="space-y-1" key={feature.label}>
                <div className="flex justify-between gap-2 text-xs text-slate-300"><span>{feature.label}</span><span>{feature.present}</span></div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-800" aria-hidden="true">
                  <div className="h-full bg-cyan-400" style={{ width: `${100 * feature.present / dataset.events}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function TrialMonitor({ run }: { run: RunDetail }): JSX.Element {
  const [chosenFold, setChosenFold] = useState<number | null>(null);
  const trials = run.progress.trials;
  const available = Array.from(new Set(trials.map((trial) => trial.fold)));
  const fold = chosenFold ?? available[available.length - 1];
  const rows = trials.filter((trial) => trial.fold === fold);
  return (
    <article className="soc-panel space-y-3 p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-slate-100">Seguimiento de Optuna</h3>
          <p className="text-sm text-slate-400">{statusLabel[run.status]} · {run.progress.completed} de {run.progress.total} ensayos</p>
        </div>
        {available.length ? (
          <label className="text-xs text-slate-300">Búsqueda
            <select className="soc-input mt-1" value={fold} onChange={(event) => setChosenFold(Number(event.target.value))}>
              {available.map((entry) => <option key={entry} value={entry}>{searchLabel(entry)}</option>)}
            </select>
          </label>
        ) : null}
      </header>
      <progress className="h-2 w-full accent-cyan-400" aria-label="Avance de Optuna" max={run.progress.total} value={run.progress.completed} />
      {run.error ? <p className="text-sm text-red-300" role="alert">{run.error}</p> : null}
      {rows.length ? (
        <>
          <div className="h-44" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 2, left: -22 }}>
                <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
                <XAxis dataKey="number" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <YAxis domain={[0, 1]} tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Tooltip contentStyle={{ background: '#0f172a', borderColor: '#334155' }} formatter={(value: number) => formatPercent(value)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="linear" dataKey="value" name="Precisión promedio" stroke="#22d3ee" dot isAnimationActive={false} />
                <Line type="stepAfter" dataKey="best" name="Mejor hasta ahora" stroke="#fbbf24" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <details className="text-sm text-slate-300">
            <summary className="cursor-pointer">Ver parámetros por ensayo</summary>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full min-w-[450px] text-left text-sm">
                <thead className="border-b border-slate-800 text-xs text-slate-400">
                  <tr><th scope="col" className="p-2">Ensayo</th><th scope="col" className="p-2">Precisión promedio</th><th scope="col" className="p-2">Parámetros</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-800">{rows.map((trial) => (
                  <tr key={trial.number}><td className="p-2">{trial.number}</td><td className="p-2">{formatPercent(trial.value)}</td><td className="p-2">{formatParams(trial.params)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </details>
        </>
      ) : null}
      {run.result ? <p className="text-sm text-slate-300">Configuración elegida · {formatParams(run.result.best_params)}.</p> : null}
    </article>
  );
}

export function AccessModels({ demoEnabled }: { demoEnabled: boolean }): JSX.Element {
  const canTrain = usePermission('access:train');
  const client = useQueryClient();
  const [config, setConfig] = useState<ModelConfiguration>({
    scope: demoEnabled ? 'demo' : 'operation', algorithm: 'logistic', days: 90, trials: 8, seed: 42,
  });
  const [selected, setSelected] = useState<number | null>(null);
  const dataset = useQuery({
    queryKey: ['access', 'model-dataset', config.scope, config.days],
    queryFn: () => accessModelsApi.dataset(config.scope, config.days),
  });
  const history = useQuery({
    queryKey: ['access', 'model-runs'], queryFn: accessModelsApi.runs,
    refetchInterval: (query) => query.state.data?.some((run) => isActive(run.status)) ? 3500 : false,
  });
  const runId = selected ?? history.data?.[0]?.id;
  const detail = useQuery({
    queryKey: ['access', 'model-run', runId], queryFn: () => accessModelsApi.run(runId!),
    enabled: runId !== undefined,
    refetchInterval: (query) => isActive(query.state.data?.status) ? 1200 : false,
  });
  const start = useMutation({
    mutationFn: accessModelsApi.start,
    onSuccess: (run) => {
      client.setQueryData(['access', 'model-run', run.id], run);
      setSelected(run.id);
      void client.invalidateQueries({ queryKey: ['access', 'model-runs'] });
    },
    onError: () => { void client.invalidateQueries({ queryKey: ['access', 'model-runs'] }); },
  });
  const active = isActive(detail.data?.status) || Boolean(history.data?.some((run) => isActive(run.status)));
  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    start.mutate(config);
  }
  return (
    <section className="space-y-5" aria-label="Modelos de detección">
      <article className="soc-panel space-y-4 p-4">
        <div>
          <h2 className="font-semibold text-slate-100">Datos y entrenamiento</h2>
          <p className="mt-1 text-sm text-slate-400">Partición temporal de días UTC en 70 % desarrollo, 15 % validación y 15 % prueba. Optuna usa cinco pliegues externos y tres internos en desarrollo.</p>
        </div>
        <form className="flex flex-wrap items-end gap-3" onSubmit={submit}>
          <label className="text-xs text-slate-300">Fuente
            <select className="soc-input mt-1" value={config.scope} onChange={(event) => setConfig({ ...config, scope: event.target.value as ModelConfiguration['scope'] })}>
              {demoEnabled ? <option value="demo">Muestra simulada de entrenamiento</option> : null}
              <option value="operation">Operación revisada</option>
            </select>
          </label>
          {config.scope === 'operation' ? (
            <label className="text-xs text-slate-300">Período
              <select className="soc-input mt-1" value={config.days} onChange={(event) => setConfig({ ...config, days: Number(event.target.value) })}>
                {[14, 30, 90, 180, 365].map((days) => <option value={days} key={days}>Últimos {days} días</option>)}
              </select>
            </label>
          ) : null}
          {canTrain ? (
            <>
              <label className="text-xs text-slate-300">Modelo
                <select className="soc-input mt-1" value={config.algorithm} onChange={(event) => setConfig({ ...config, algorithm: event.target.value as ModelConfiguration['algorithm'] })}>
                  <option value="logistic">Regresión logística</option><option value="tree">Árbol de decisión</option>
                </select>
              </label>
              <label className="w-32 text-xs text-slate-300">Ensayos por búsqueda
                <input className="soc-input mt-1" type="number" required min={3} max={25} value={config.trials}
                  onChange={(event) => setConfig({ ...config, trials: Number(event.target.value) })} />
              </label>
              <label className="w-24 text-xs text-slate-300">Semilla
                <input className="soc-input mt-1" type="number" required min={0} max={999999} value={config.seed}
                  onChange={(event) => setConfig({ ...config, seed: Number(event.target.value) })} />
              </label>
              <button className="soc-btn-primary" type="submit" disabled={start.isPending || active || !dataset.data || Boolean(dataset.data.reason)}>
                {start.isPending ? 'Encolando…' : 'Entrenar modelo'}
              </button>
            </>
          ) : null}
        </form>
        {canTrain ? <p className="text-xs text-slate-400">
          {config.algorithm === 'logistic'
            ? 'Búsqueda de C entre 0,015 y 40 en escala logarítmica, con o sin ponderación de clases.'
            : 'Búsqueda de profundidad entre 2 y 9, mínimo de 2 a 20 eventos por hoja, criterio Gini o entropía y ponderación opcional.'}
        </p> : null}
        {config.scope === 'demo' ? (
          <p className="text-xs text-slate-400">La muestra de entrenamiento es simulada y se genera aparte de los siete escenarios de la demo de reglas.</p>
        ) : <p className="text-xs text-slate-400">Usa las etiquetas guardadas en Eventos y anomalías. Cada partición y pliegue necesita ambas clases.</p>}
        {start.isError ? <p className="text-sm text-red-300" role="alert">{getErrorMessage(start.error)}</p> : null}
        {dataset.isPending ? <Loading label="Cargando datos…" /> : null}
        {dataset.isError ? <ErrorState message={getErrorMessage(dataset.error)} onRetry={() => void dataset.refetch()} /> : null}
        {dataset.data ? <DatasetDetails dataset={dataset.data} /> : null}
      </article>
      {history.isError ? <ErrorState message={getErrorMessage(history.error)} onRetry={() => void history.refetch()} /> : null}
      {history.data?.length ? (
        <section className="space-y-4" aria-label="Historial de ejecuciones">
          <div className="soc-panel p-4">
            <label className="block max-w-xl text-xs text-slate-300">Ejecución
              <select className="soc-input mt-1" value={runId} onChange={(event) => setSelected(Number(event.target.value))}>
                {history.data.map((run) => (
                  <option value={run.id} key={run.id}>{run.id} · {algorithmLabel[run.configuration.algorithm]} · {scopeLabel[run.configuration.scope]} · {statusLabel[run.status]} · {formatDateTime(run.created_at)}</option>
                ))}
              </select>
            </label>
          </div>
          {detail.isPending ? <Loading label="Cargando ejecución…" /> : null}
          {detail.isError ? <ErrorState message={getErrorMessage(detail.error)} onRetry={() => void detail.refetch()} /> : null}
          {detail.data ? <TrialMonitor key={detail.data.id} run={detail.data} /> : null}
          {detail.data?.result ? <AccessModelResults run={{ ...detail.data, result: detail.data.result }} /> : null}
        </section>
      ) : history.data ? <EmptyState title="Sin ejecuciones" description="Entrena un modelo para consultar los ensayos y la evaluación en prueba." /> : null}
    </section>
  );
}
