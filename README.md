# PachyMove

Boîte à outils pour préparer une migration PostgreSQL majeure (ex. PG14 → PG18). Un même moteur CLI, `pgaudit-runner`, exécute des modules déclarés en manifeste YAML : chacun trace ses résultats dans un JSON horodaté, puis génère un rapport Markdown. Conçu pour être réutilisable d'une mission à l'autre sans toucher au code Python.

---

## Modules

| Module | Manifeste | Usage |
|---|---|---|
| **Pré-audit migration** | `pg14_to_pg18.yaml` | Inventaire (bases, config serveur, rôles, extensions, FDW, colonnes générées, publications…) **+ détection des bloquants de migration** : Famille A (`--tags bloquant`, ex. collations, checksums, index invalides) et Famille B, delta 15→18 (`--tags delta`, ex. `search_path`, droits par défaut sur `public`) |
| **Audit des droits** | `rights_audit.yaml` | Cartographie des privilèges PostgreSQL — ACL directs, hérités de groupe (résolution récursive), propriété, signalement RLS. Générique, réutilisable hors contexte de migration. |

Chaque module s'exécute avec la même CLI, en changeant simplement `--manifest`. La partie diff (comparer la matrice de droits à une cible YAML et générer les `GRANT`/`REVOKE` correctifs) est volontairement hors scope de l'audit des droits actuel — nature différente (comparaison + génération de code, pas lecture seule + rapport), à construire en outil séparé une fois une matrice réelle validée en mission.

Convention pour la détection des bloquants : **zéro ligne renvoyée = sain**. `--tags bloquant` donne un run rapide de type « est-ce que je peux y aller ».
Note : `shared_preload_libraries` est un inventaire (renvoie des lignes même quand tout va bien) ; `public_schema_create_acl` est une requête informative taguée `delta` ; voir `.tydata/specs/specs_detection_migration_1.md`.

---

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

pip install -e .
# ou, pour lancer les tests : pip install -e .[dev]
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
| `--tags bloquant` | Run rapide « est-ce que je peux y aller » (Famille A, module Pré-audit migration) |
| `--tags delta` | Delta 15→18 (Famille B, module Pré-audit migration) |
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

### Export CSV (optionnel)

Pour filtrer un résultat en tableur (utile notamment pour la matrice de droits, souvent trop volumineuse pour le rapport Markdown tronqué) :

```powershell
python scripts/export_csv.py output/audit_20260612_143022.json --output-dir output/csv/
```

Écrit un `.csv` par requête réussie du JSON, sans dépendance supplémentaire.

---

## Structure du projet

```
PachyMove/
├── pgaudit_runner/         # code Python — moteur CLI commun à tous les modules
├── queries/
│   ├── instance/           # exécutées une fois (rôles, config, groupes, bases…)
│   └── database/           # exécutées par base ciblée (extensions, FDW, droits…)
├── manifests/
│   ├── pg14_to_pg18.yaml   # module Pré-audit migration
│   └── rights_audit.yaml   # module Audit des droits
├── scripts/
│   └── export_csv.py       # export CSV d'un JSON d'audit (filtrage tableur)
├── tests/                  # suite pytest (config, models, runner, reporter, intégration)
└── output/                 # JSON + rapports générés (gitignore)
```

---

## Tests & CI

```bash
pip install -e .[dev]
pytest
```

CI GitHub Actions minimaliste (`.github/workflows/ci.yml`) : `pytest` sur push vers `main` et sur chaque pull request.

---

## Ajouter une requête

1. Créer le fichier SQL dans `queries/instance/` ou `queries/database/`.
2. Ajouter une entrée dans le manifeste YAML du module concerné :

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

- `read_only: true` (défaut) : toute requête contenant `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT` ou `REVOKE` est rejetée avant exécution (garde-fou purement textuel).
- Le mot de passe n'apparaît jamais dans le JSON de sortie ni dans les logs.
- Recommandation : utiliser un rôle PostgreSQL en lecture seule côté serveur, en complément du garde-fou applicatif (néanmoins, certaines requêtes nécessitant un accès superuser seront bypassées).
