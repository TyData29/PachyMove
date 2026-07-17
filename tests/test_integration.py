from __future__ import annotations

from pathlib import Path

import pytest

from pgaudit_runner.collector import collect
from pgaudit_runner.reporter import generate_report

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MANIFESTS = sorted((REPO_ROOT / "manifests").glob("*.yaml"))


@pytest.mark.parametrize("manifest_path", REAL_MANIFESTS, ids=lambda p: p.name)
def test_collect_dry_run_then_report_on_real_manifests(tmp_path: Path, manifest_path: Path):
    """Aucune connexion réelle requise : couvre bout-en-bout chargement du manifeste,
    sélection des requêtes et génération du rapport pour chaque manifeste du dépôt."""
    output_file = collect(
        host="unused", port=5432, user="unused",
        dbnames=["db1"], maintenance_db="postgres",
        manifest_path=manifest_path,
        queries_dir=REPO_ROOT / "queries",
        output_dir=tmp_path,
        tags=[], only=[], exclude=[],
        dry_run=True,
    )

    assert output_file.exists()

    report = generate_report(output_file)
    assert "# Rapport de pré-audit PostgreSQL" in report
    assert "⏭️" in report  # tout est "skipped" en dry-run
