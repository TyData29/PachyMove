# pgaudit-runner

Outil CLI de pré-audit PostgreSQL avant migration majeure (ex. PG14 → PG18).

Exécute un jeu de requêtes SQL déclarées dans un manifeste YAML, trace chaque résultat dans un fichier JSON horodaté, puis génère un rapport Markdown. Conçu pour être réutilisable d'une mission à l'autre sans toucher au code Python.

---

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -e .
```

**Dépendances :** Python ≥ 3.10 · psycopg v3 · PyYAML · click

---

## Utilisation

### 1. Collecter (connexion à la base)

```powershell
pgaudit-runner collect `
  --host srv-pg-prod `
  --port 5432 `
  --user mon_user `
  --dbnames bd1,bd2 `
  --manifest manifests/pg14_to_pg18.yaml `
  --output output/
```

Produit : `output/audit_<YYYYMMDD>_<HHMMSS>.json`

### 2. Générer le rapport (sans connexion)

```powershell
pgaudit-runner report `
  --input output/audit_20260612_143022.json `
  --output output/rapport_20260612.md
```

### Options utiles de `collect`

| Option | Description |
|---|---|
| `--tags fdw,inventaire` | N'exécute que les requêtes portant ces tags |
| `--only list_databases,roles` | Exécute uniquement ces ids |
| `--exclude postgis_version` | Exclut ces ids |
| `--maintenance-db postgres` | Base de connexion pour les requêtes `scope: instance` (défaut : `postgres`) |
| `--service nom` | Utilise un profil `pg_service.conf` |
| `--dry-run` | Simule sans connexion réelle (vérifie ce qui serait lancé) |

### Mot de passe

Le mot de passe n'est jamais passé en argument. Ordre de résolution :
1. Variable d'environnement `PGPASSWORD`
2. Fichier `~/.pgpass`
3. `pg_service.conf` via `--service`
4. Prompt interactif masqué

---

## Structure du projet

```
pgaudit-runner/
├── pgaudit_runner/         # code Python
├── queries/
│   ├── instance/           # exécutées une fois (rôles, config, bases…)
│   └── database/           # exécutées par base ciblée (extensions, FDW…)
├── manifests/
│   └── pg14_to_pg18.yaml   # manifeste : quelles requêtes, activées ou non
└── output/                 # JSON + rapports générés (gitignore)
```

---

## Ajouter une requête

1. Créer le fichier SQL dans `queries/instance/` ou `queries/database/`.
2. Ajouter une entrée dans le manifeste YAML :

```yaml
- id: sequences
  title: "Séquences et valeurs courantes"
  file: database/sequences.sql
  scope: database
  enabled: true
  tags: [inventaire, schema]
```

Aucune modification de code Python.

---

## Format du manifeste

```yaml
meta:
  name: "Pré-audit migration PG14 → PG18"

defaults:
  statement_timeout_ms: 30000   # timeout par requête
  read_only: true               # refuse tout SQL d'écriture

queries:
  - id: mon_check               # identifiant unique
    title: "Mon contrôle"
    file: database/mon_check.sql
    scope: database             # "instance" ou "database"
    enabled: true
    tags: [schema]
    requires_superuser: false
    skip_reason_if_disabled: "Raison affichée si enabled: false"
```

---

## Sécurité

- `read_only: true` (défaut) : toute requête contenant `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT` ou `REVOKE` est rejetée avant exécution.
- Le mot de passe n'apparaît jamais dans le JSON de sortie ni dans les logs.
- Recommandation : utiliser un rôle PostgreSQL en lecture seule côté serveur, en complément du garde-fou applicatif.
