from __future__ import annotations

from qgisaudit_runner.database import chemin_projet


def test_chemin_projet_with_service_follows_qgis_uri():
    assert chemin_projet("service=sig_prod user=moi password=secret", "qgis", "Plan") == (
        "postgresql:///?service=sig_prod&schema=qgis&project=Plan"
    )


def test_chemin_projet_without_service_hides_credentials():
    chemin = chemin_projet("host=10.0.0.5 dbname=sig user=moi password=secret", "qgis", "Plan")
    assert chemin == "postgresql://10.0.0.5:5432/?dbname=sig&schema=qgis&project=Plan"
    assert "secret" not in chemin and "moi" not in chemin
