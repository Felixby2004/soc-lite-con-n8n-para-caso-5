import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { accessApi, type AccessIndicator } from '@/api/access';
import { ConfirmDialog } from '@/components/Modal';
import { Pagination } from '@/components/Pagination';
import { EmptyState, ErrorState, Loading } from '@/components/States';
import { useToast } from '@/components/Toast';
import { usePermission } from '@/context/AuthContext';
import { getErrorMessage } from '@/utils/errors';
import { formatDateTime } from '@/utils/format';

const emptyForm = { ip_address: '', reference: '', ttl_days: '30' };

export function AccessIndicators(): JSX.Element {
  const canWrite = usePermission('access:ioc');
  const client = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  const [revoking, setRevoking] = useState<AccessIndicator | null>(null);
  const indicators = useQuery({
    queryKey: ['access', 'indicators', page],
    queryFn: () => accessApi.indicators(page),
  });
  const refresh = (): void => {
    setPage(1);
    void client.invalidateQueries({ queryKey: ['access', 'indicators'] });
    void client.invalidateQueries({ queryKey: ['access', 'summary'] });
  };
  const save = useMutation({
    mutationFn: accessApi.saveIndicator,
    onSuccess: () => {
      setForm(emptyForm);
      setError('');
      refresh();
      toast.success('Indicador guardado');
    },
    onError: (failure) => setError(getErrorMessage(failure)),
  });
  const revoke = useMutation({
    mutationFn: accessApi.revokeIndicator,
    onSuccess: () => {
      setRevoking(null);
      refresh();
      toast.success('Indicador revocado');
    },
    onError: (failure) => {
      setRevoking(null);
      toast.error('No se pudo revocar', getErrorMessage(failure));
    },
  });

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setError('');
    save.mutate({ ip_address: form.ip_address.trim(), reference: form.reference.trim(), ttl_days: Number(form.ttl_days) });
  }

  return (
    <div className="space-y-4">
      {canWrite ? (
        <form className="soc-panel space-y-3 p-4" onSubmit={submit}>
          <div>
            <h2 className="font-semibold text-slate-100">Registrar o renovar indicador</h2>
            <p className="mt-1 text-sm text-slate-400">Guardar una IP existente reemplaza su referencia y reinicia su vigencia.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-300">Dirección IP
              <input className="soc-input mt-1" required maxLength={45} value={form.ip_address} placeholder="192.0.2.10"
                onChange={(event) => setForm({ ...form, ip_address: event.target.value })} />
            </label>
            <label className="min-w-48 grow text-xs text-slate-300">Fuente o referencia
              <input className="soc-input mt-1" required maxLength={240} value={form.reference} placeholder="Ej. incidente interno"
                onChange={(event) => setForm({ ...form, reference: event.target.value })} />
            </label>
            <label className="w-28 text-xs text-slate-300">Vigencia (días)
              <input className="soc-input mt-1" type="number" required min={1} max={365} value={form.ttl_days}
                onChange={(event) => setForm({ ...form, ttl_days: event.target.value })} />
            </label>
            <button className="soc-btn-primary" type="submit" disabled={save.isPending}>{save.isPending ? 'Guardando…' : 'Guardar indicador'}</button>
          </div>
          {error ? <p className="text-sm text-red-300" role="alert">{error}</p> : null}
        </form>
      ) : null}
      <section className="soc-panel">
        {indicators.isPending ? <Loading label="Cargando indicadores…" /> : null}
        {indicators.isError ? <ErrorState message={getErrorMessage(indicators.error)} onRetry={() => void indicators.refetch()} /> : null}
        {indicators.data && (indicators.data.items.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-800 text-xs text-slate-400">
                <tr>{['IP', 'Referencia', 'Vence', 'Estado', ...(canWrite ? ['Acciones'] : [])].map((label) =>
                  <th scope="col" className="px-4 py-3" key={label}>{label}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-slate-300">
                {indicators.data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-100">{row.ip_address}</td>
                    <td className="min-w-40 max-w-96 break-words px-4 py-3">{row.reference}</td>
                    <td className="whitespace-nowrap px-4 py-3">{formatDateTime(row.expires_at)}</td>
                    <td className={`px-4 py-3 ${row.active ? 'text-emerald-300' : 'text-slate-400'}`}>{row.active ? 'Vigente' : 'Inactivo'}</td>
                    {canWrite ? (
                      <td className="px-4 py-3">
                        {row.active ? <button className="text-sm font-medium text-red-300 hover:underline" type="button" onClick={() => setRevoking(row)}>Revocar</button> : '—'}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState title="Sin indicadores IP" description="Los indicadores registrados y su vigencia aparecerán aquí." />)}
        {indicators.data ? <Pagination page={page} pages={indicators.data.pages} onChange={setPage} /> : null}
      </section>
      <ConfirmDialog open={revoking !== null} title="Revocar indicador" tone="danger"
        message={`La IP ${revoking?.ip_address ?? ''} dejará de contribuir al puntaje de nuevos accesos.`}
        confirmLabel="Revocar" loading={revoke.isPending} onCancel={() => setRevoking(null)}
        onConfirm={() => { if (revoking) revoke.mutate(revoking.id); }} />
    </div>
  );
}
