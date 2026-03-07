from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from sqlalchemy import desc

from app.db import SessionLocal
from app.models import Job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export qualified jobs to CSV")
    parser.add_argument("--min-score", type=float, default=70.0, help="Minimum interview probability")
    parser.add_argument("--limit", type=int, default=500, help="Maximum rows to export")
    parser.add_argument("--output", type=str, default="", help="Optional output CSV path")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = Path("results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"jobs_export_{timestamp}.csv"

    db = SessionLocal()
    try:
        rows = (
            db.query(Job)
            .filter(Job.interview_probability >= args.min_score)
            .order_by(desc(Job.interview_probability), desc(Job.created_at))
            .limit(args.limit)
            .all()
        )

        with output_path.open("w", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(
                [
                    "job_id",
                    "title",
                    "company",
                    "location",
                    "url",
                    "source",
                    "posted_time",
                    "interview_probability",
                    "salary_fit_probability",
                    "stack_match",
                    "is_super_priority",
                    "is_ultra_low_competition",
                    "apply_within_6_hours",
                ]
            )
            for job in rows:
                writer.writerow(
                    [
                        job.job_id,
                        job.title,
                        job.company,
                        job.location,
                        job.url,
                        job.source,
                        job.posted_time.isoformat() if job.posted_time else "",
                        job.interview_probability,
                        job.salary_fit_probability,
                        job.stack_match,
                        job.is_super_priority,
                        job.is_ultra_low_competition,
                        job.apply_within_6_hours,
                    ]
                )

        print(f"Exported {len(rows)} rows to {output_path.resolve()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
