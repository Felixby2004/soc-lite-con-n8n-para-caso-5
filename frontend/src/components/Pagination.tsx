import { ChevronLeft, ChevronRight } from 'lucide-react';

export function Pagination({ page, pages, onChange }: {
  page: number; pages: number; onChange: (page: number) => void;
}): JSX.Element | null {
  if (pages <= 1 && page <= 1) return null;
  return (
    <nav className="flex items-center justify-end gap-2 p-3 text-sm text-slate-400" aria-label="Paginación">
      <button className="soc-btn-secondary" type="button" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Página anterior">
        <ChevronLeft size={16} />
      </button>
      <span>Página {page} de {Math.max(pages, 1)}</span>
      <button className="soc-btn-secondary" type="button" disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Página siguiente">
        <ChevronRight size={16} />
      </button>
    </nav>
  );
}
