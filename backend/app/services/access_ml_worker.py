"""Proceso de entrenamiento. PostgreSQL conserva la cola y el avance."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.models import AccessModelRun
from app.schemas.access_ml import ModelConfiguration
from app.services.access_ml_data import OUTER_FOLDS, load_training_data
from app.services.access_ml_training import train_model

logger = logging.getLogger(__name__)
WORKER_LOCK = 60520261112


async def save(run_id: int, **values) -> None:
    async with AsyncSessionLocal.begin() as db:
        await db.execute(update(AccessModelRun).where(
            AccessModelRun.id == run_id, AccessModelRun.status == "running",
        ).values(**values))


async def next_run() -> tuple[int, dict, datetime] | None:
    async with AsyncSessionLocal.begin() as db:
        row = await db.scalar(
            select(AccessModelRun).where(AccessModelRun.status == "queued")
            .order_by(AccessModelRun.id).limit(1).with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        now = datetime.now(timezone.utc)
        row.status = "running"
        row.started_at = now
        return row.id, row.configuration, now


async def execute(run_id: int, configuration: dict, started: datetime) -> None:
    loop = asyncio.get_running_loop()
    trials = []
    config = ModelConfiguration.model_validate(configuration)
    total_trials = (OUTER_FOLDS + 1) * config.trials

    def record(trial: dict) -> None:
        trials.append(trial)
        progress = {"completed": len(trials), "total": total_trials, "trials": list(trials)}
        asyncio.run_coroutine_threadsafe(save(run_id, progress=progress), loop).result()

    try:
        if config.scope == "demo" and not settings.DEMO_MODE:
            raise ValueError("La fuente simulada requiere habilitar la demostración.")
        async with AsyncSessionLocal() as db:
            rows, total = await load_training_data(db, config.scope, config.days, started)
        result, artifact = await asyncio.to_thread(train_model, rows, total, config, record)
        await save(run_id, status="completed", result=result, artifact=artifact, finished_at=datetime.now(timezone.utc))
    except ValueError as error:
        await save(run_id, status="failed", error=str(error), finished_at=datetime.now(timezone.utc))
    except Exception:
        logger.exception("Falló el entrenamiento %s", run_id)
        await save(run_id, status="failed", error="El trabajador no pudo completar el entrenamiento.",
                   finished_at=datetime.now(timezone.utc))


async def serve() -> None:
    while True:
        try:
            async with engine.connect() as connection:
                ready = await connection.scalar(select(func.to_regclass("access_model_runs")))
                locked = ready and await connection.scalar(select(func.pg_try_advisory_lock(WORKER_LOCK)))
                await connection.commit()
                if locked:
                    try:
                        async with AsyncSessionLocal.begin() as db:
                            await db.execute(update(AccessModelRun).where(AccessModelRun.status == "running").values(
                                status="failed", error="La ejecución se interrumpió. Inicia una nueva para reintentar.",
                                finished_at=datetime.now(timezone.utc),
                            ))
                        while True:
                            # Comprueba que sigue activa la conexión dueña del bloqueo.
                            await connection.execute(select(1))
                            await connection.commit()
                            run = await next_run()
                            if run:
                                await execute(*run)
                            else:
                                await asyncio.sleep(2)
                    finally:
                        await connection.execute(select(func.pg_advisory_unlock(WORKER_LOCK)))
                        await connection.commit()
        except Exception:
            logger.exception("Trabajador de accesos desconectado. Se volverá a intentar.")
        await asyncio.sleep(3)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
