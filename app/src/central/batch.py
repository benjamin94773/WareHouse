"""Batch diario: python batch.py [--date AAAA-MM-DD] (por defecto, hoy en UTC). Lo programa cron a las 23:00."""
import argparse
from datetime import datetime, timezone

from shared.observability import setup_logging

setup_logging()

from db import Base, engine  # noqa: E402
from reports import create_job, run_job  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    job_id = create_job(args.date, trigger="cli")
    run_job(job_id)
    print(job_id)
