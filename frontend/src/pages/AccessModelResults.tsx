import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { accessModelsApi, type ModelMetrics, type ModelResult, type Partitions, type RunDetail } from '@/api/accessModels';
import { ExportMenu } from '@/components/ExportMenu';
import { usePermission } from '@/context/AuthContext';
import { getErrorMessage } from '@/utils/errors';

const percent = new Intl.NumberFormat('es-PE', { style: 'percent', maximumFractionDigits: 1 });
const number = new Intl.NumberFormat('es-PE', { maximumFractionDigits: 3 });
const partitions = { development: 'Desarrollo', validation: 'Validación', test: 'Prueba' };
const severity = { medium: 'Media', high: 'Alta', critical: 'Crítica' };
export const algorithmLabel = { logistic: 'Regresión logística', tree: 'Árbol de decisión' };
export const scopeLabel = { demo: 'Simulada', operation: 'Operativa' };

export function formatPercent(value: number | null): string {
  return value === null ? 'Sin base' : percent.format(value);
}

export function PartitionTable({ data }: { data: Partitions }): JSX.Element {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[430px] text-left text-sm text-slate-200">
        <thead className="border-b border-slate-800 text-xs text-slate-400">
          <tr>{['Partición', 'Eventos', 'Esperados', 'Anómalos', 'Días UTC'].map((label) => <th scope="col" className="p-2" key={label}>{label}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {(Object.keys(partitions) as Array<keyof Partitions>).map((key) => (
            <tr key={key}>
              <th scope="row" className="p-2 font-medium">{partitions[key]}</th>
              <td className="p-2">{data[key].events}</td><td className="p-2">{data[key].expected}</td>
              <td className="p-2">{data[key].anomalous}</td><td className="p-2">{data[key].days}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Curve({ result, type }: { result: ModelResult; type: 'roc' | 'pr' }): JSX.Element {
  const xLabel = type === 'roc' ? 'Tasa de falsos positivos' : 'Sensibilidad';
  const yLabel = type === 'roc' ? 'Sensibilidad' : 'Precisión';
  return (
    <article className="soc-panel min-w-0 space-y-2 p-4">
      <h4 className="font-semibold text-slate-100">{type === 'roc' ? 'Curva ROC' : 'Curva precisión sensibilidad'}</h4>
      <p className="text-xs text-slate-400">{xLabel} en el eje horizontal · {yLabel} en el eje vertical</p>
      <div className="h-56" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart margin={{ top: 10, right: 12, bottom: 5, left: -22 }}>
            <CartesianGrid stroke="#243044" strokeDasharray="3 3" />
            <XAxis type="number" dataKey="x" domain={[0, 1]} tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <YAxis type="number" dataKey="y" domain={[0, 1]} tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#0f172a', borderColor: '#334155' }} formatter={(value: number) => formatPercent(value)} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line data={result.model[type]} dataKey="y" name="Modelo" stroke="#22d3ee" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line data={result.heuristic[type]} dataKey="y" name="Heurística" stroke="#fbbf24" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

function CompareMetrics({ result }: { result: ModelResult }): JSX.Element {
  const labels = [
    ['ROC AUC', 'roc_auc'], ['Precisión promedio', 'average_precision'], ['Precisión al umbral', 'precision'],
    ['Sensibilidad', 'recall'], ['Especificidad', 'specificity'], ['F1', 'f1'], ['Exactitud', 'accuracy'],
  ] as const;
  const confusion = (method: ModelMetrics): string =>
    `${method.confusion.true_positive} / ${method.confusion.false_positive} / ${method.confusion.false_negative} / ${method.confusion.true_negative}`;
  return (
    <article className="soc-panel min-w-0 space-y-3 p-4">
      <h4 className="font-semibold text-slate-100">Métricas en prueba</h4>
      <div className="overflow-x-auto">
        <table className="w-full min-w-72 text-left text-sm text-slate-200">
          <thead className="border-b border-slate-800 text-xs text-slate-400">
            <tr><th scope="col" className="p-2">Medida</th><th scope="col" className="p-2">Modelo</th><th scope="col" className="p-2">Heurística</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {labels.map(([label, key]) => <tr key={key}>
              <th scope="row" className="p-2 font-medium">{label}</th>
              <td className="p-2">{formatPercent(result.model[key])}</td><td className="p-2">{formatPercent(result.heuristic[key])}</td>
            </tr>)}
            <tr><th scope="row" className="p-2 font-medium">VP / FP / FN / VN</th><td className="p-2">{confusion(result.model)}</td><td className="p-2">{confusion(result.heuristic)}</td></tr>
            <tr><th scope="row" className="p-2 font-medium">Umbral</th><td className="p-2">{formatPercent(result.model.threshold)}</td><td className="p-2">50/100</td></tr>
          </tbody>
        </table>
      </div>
    </article>
  );
}

function PredictAccess({ id }: { id: number }): JSX.Element {
  const [json, setJson] = useState('');
  const prediction = useMutation({
    mutationFn: async (text: string) => {
      let payload: unknown;
      try { payload = JSON.parse(text); } catch { throw new Error('El contenido debe ser JSON válido.'); }
      return accessModelsApi.predict(id, payload);
    },
  });
  function example(): void {
    setJson(JSON.stringify({
      source: 'vpn-corporativa',
      events: [{ event_id: 'prueba-001', account: 'cuenta-prueba', occurred_at: new Date().toISOString(), outcome: 'failure', network: 'vpn' }],
    }, null, 2));
    prediction.reset();
  }
  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    prediction.mutate(json);
  }
  const data = prediction.data;
  return (
    <article className="soc-panel space-y-3 p-4">
      <h4 className="font-semibold text-slate-100">Inferencia individual</h4>
      <p className="text-sm text-slate-400">Evalúa un evento con esta ejecución. El acceso se procesa en modo de simulación.</p>
      <form className="space-y-2" onSubmit={submit}>
        <label className="block text-xs text-slate-300">JSON de un acceso
          <textarea className="soc-input mt-1 min-h-28 font-mono text-xs" value={json} required maxLength={12_000}
            onChange={(event) => { setJson(event.target.value); prediction.reset(); }} />
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="soc-btn-secondary" onClick={example} disabled={prediction.isPending}>Usar ejemplo</button>
          <button type="submit" className="soc-btn-primary" disabled={!json.trim() || prediction.isPending}>{prediction.isPending ? 'Evaluando…' : 'Evaluar con modelo'}</button>
        </div>
      </form>
      {prediction.isError ? <p className="text-sm text-red-300" role="alert">{getErrorMessage(prediction.error)}</p> : null}
      {data ? (
        <section className="space-y-3 rounded-lg border border-slate-800 p-3" aria-live="polite">
          <p className="font-semibold text-cyan-200">
            Puntaje del modelo {formatPercent(data.probability)} · {data.severity ? `Severidad orientativa ${severity[data.severity]}` : 'Por debajo del umbral'}
          </p>
          <p className="text-sm text-slate-400">Umbral {formatPercent(data.threshold)} · Puntaje heurístico {data.heuristic.score}/100 · {data.heuristic.baseline_size} accesos en el historial.</p>
          <p className="text-xs text-slate-400">Cada aporte compara el puntaje con el que se obtiene al sustituir ese atributo por su mediana de desarrollo. Los efectos son locales y pueden interactuar.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-80 text-left text-sm text-slate-300">
              <thead className="border-b border-slate-800 text-xs text-slate-400">
                <tr><th scope="col" className="p-2">Atributo</th><th scope="col" className="p-2">Valor</th><th scope="col" className="p-2">Referencia</th><th scope="col" className="p-2">Diferencia (pp)</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800">{data.contributions.map((item) => (
                <tr key={item.code}>
                  <th scope="row" className="p-2 font-medium">{item.label}</th><td className="p-2">{number.format(item.value)}</td>
                  <td className="p-2">{number.format(item.reference)}</td><td className="p-2 font-mono text-cyan-200">{item.delta > 0 ? '+' : ''}{number.format(item.delta * 100)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      ) : null}
    </article>
  );
}

export function AccessModelResults({ run }: { run: RunDetail & { result: ModelResult } }): JSX.Element {
  const canExport = usePermission('reports:export');
  const canPredict = usePermission('access:write');
  const result = run.result;
  const paired = result.paired;
  return (
    <section className="space-y-4" aria-label="Resultados del modelo">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-slate-100">Resultados de la ejecución {run.id}</h3>
          <p className="text-sm text-slate-400">{algorithmLabel[run.configuration.algorithm]} · Fuente {scopeLabel[run.configuration.scope].toLowerCase()} · {result.partitions.test.events} eventos de prueba</p>
        </div>
        {canExport ? (
          <ExportMenu contextLabel="Evaluación del modelo" options={(['pdf', 'docx', 'xlsx'] as const).map((format) => ({
            format, onExport: () => accessModelsApi.export(run.id, format),
          }))} />
        ) : null}
      </header>
      <div className="grid gap-4 xl:grid-cols-2">
        <CompareMetrics result={result} />
        <article className="soc-panel space-y-3 p-4">
          <h4 className="font-semibold text-slate-100">Comparación pareada en prueba</h4>
          <dl className="grid grid-cols-2 gap-3 text-sm text-slate-300">
            <div><dt className="text-xs text-slate-400">Diferencia de exactitud</dt><dd>{number.format(paired.difference * 100)} pp</dd></div>
            <div><dt className="text-xs text-slate-400">Intervalo bootstrap 95 %</dt><dd>{paired.interval ? paired.interval.map((value) => `${number.format(value * 100)} pp`).join(' a ') : 'Sin base'}</dd></div>
            <div><dt className="text-xs text-slate-400">p por permutación de signos</dt><dd>{paired.p_value === null ? 'Sin base' : paired.p_value.toFixed(4)}</dd></div>
            <div><dt className="text-xs text-slate-400">Bloques</dt><dd>{paired.days} días UTC</dd></div>
          </dl>
          <p className="text-xs text-slate-400">La comparación usa los mismos accesos para ambos métodos y agrupa por día. Su interpretación depende de la representatividad y de la dependencia entre días.</p>
        </article>
        <Curve type="roc" result={result} />
        <Curve type="pr" result={result} />
      </div>
      <details className="soc-panel p-4 text-sm text-slate-300">
        <summary className="cursor-pointer font-semibold text-slate-100">Particiones y validación cruzada externa</summary>
        <div className="mt-3 space-y-3">
          <PartitionTable data={result.partitions} />
          <p>Precisión promedio externa {formatPercent(result.mean_outer_ap)}.</p>
          <ul className="flex flex-wrap gap-2">
            {result.outer_folds.map((fold) => <li className="rounded-md border border-slate-800 p-2" key={fold.fold}>Pliegue {fold.fold} · {formatPercent(fold.average_precision)}</li>)}
          </ul>
          <p className="break-all text-xs">SHA-256 de la muestra {result.dataset_sha256}</p>
        </div>
      </details>
      {canPredict ? <PredictAccess key={run.id} id={run.id} /> : null}
    </section>
  );
}
