# PachyMove

Boîte à outils pour auditer une base de données PostgreSQL/PostGIS et/ou préparer une migration PostgreSQL majeure (ex. PG14 → PG18). 
Un même moteur CLI, `pgaudit-runner`, exécute des modules déclarés en manifeste YAML : chacun trace ses résultats dans un JSON horodaté, puis génère un rapport Markdown.
Conçu pour être facilement adaptable sans toucher au code Python.

---

## Modules

| Module | Manifeste | Usage |
|---|---|---|
| **Pré-audit migration** | `pg14_to_pg18.yaml` | Inventaire (bases, config serveur, rôles, extensions, FDW, colonnes générées, publications…) **+ détection des bloquants de migration** : Famille A (`--tags bloquant`, ex. collations, checksums, index invalides) et Famille B, delta 15→18 (`--tags delta`, ex. `search_path`, droits par défaut sur `public`) |
| **Audit des droits** | `rights_audit.yaml` | Cartographie des privilèges PostgreSQL — ACL directs, hérités de groupe (résolution récursive), propriété, signalement RLS. Générique, réutilisable hors contexte de migration. |
| **Contrôle qualité des données** | `data_quality.yaml` | Healthcheck PostGIS (SRID, type générique, index spatial, contrainte de validité — indicateurs indirects), tables sans PK, VACUUM/bloat en retard, convention de nommage `snake_case`, séquences proches de leur limite, colonnes `*_id` sans FK déclarée, tables sans commentaire, tables en doublon entre schémas (nom/structure), classement des tables les plus accédées. Générique, indépendant d'une migration, catalogue seul. |
| **Contrôle qualité — scan par table** | `data_quality_on_tables.yaml` | Vrai scan de données (plus lent, `--tags scan`) : colonnes peu remplies (< 10 %), colonnes à valeur constante, géométries réellement invalides, tables potentiellement dépréciées (aucune activité depuis 6 mois/1 an/3 ans), vrais doublons de tables (contenu identique). Échantillonne les grosses tables (`TABLESAMPLE SYSTEM`) sur les deux premiers contrôles. Attention : peut être très long sur de grandes bases de données |

Chaque module s'exécute avec la même CLI, en changeant simplement `--manifest`.

### Analyse des logs de connexion (hors manifeste)

`pgaudit-runner analyze-logs` — synthèse des connexions par rôle depuis des logs PostgreSQL (`log_connections`), pas une base vivante : pas de manifeste, pas de connexion réseau.

```powershell
pgaudit-runner analyze-logs --input-dir chemin/vers/logs --output output/connexions.json
```

**Limite assumée** : avec `log_connections` seul, la sortie donne qui/quand/depuis où/quelle base — ni la durée de session (nécessite `log_disconnections`), ni le détail des actions/tables (nécessite `log_statement` ou `pgaudit`). Sortie JSON indexée par rôle, croisable avec `role_membership_tree` de `rights_audit.json` (jointure sur le nom de rôle). Toute ligne au format non reconnu est comptée et échantillonnée (`unparsed_sample`) plutôt que silencieusement ignorée — signal si le `log_line_prefix` réel diverge du défaut PostgreSQL supposé (`%m [%p] `).

---

## Installation

```bash
git clone https://github.com/TyData29/PachyMove.git
cd PachyMove

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

python -m pip install --upgrade pip
pip install -e .
# ou, pour lancer les tests : pip install -e .[dev]
```

**Dépendances :** Python ≥ 3.10 · psycopg v3 · PyYAML · click · Markdown

> **Dépannage** — erreur `File "setup.py" not found` (ou toute erreur pendant `pip install -e .`) : le projet n'a pas de `setup.py`, il utilise le format moderne `pyproject.toml` seul. Une version de `pip` trop ancienne ne sait pas l'installer en mode éditable. La commande `python -m pip install --upgrade pip` ci-dessus corrige ce cas — à relancer si l'installation a été tentée avant.

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

Produit : `output/audit_<manifeste>_<YYYYMMDD>_<HHMMSS>.json` **et** `output/rapport_<manifeste>_<YYYYMMDD>_<HHMMSS>.md` (le rapport Markdown est généré automatiquement après la collecte — `--no-with-report` pour ne produire que le JSON). `<manifeste>` est le nom de fichier du manifeste sans extension (ex. `pg14_to_pg18`), utile pour distinguer les runs quand plusieurs manifestes sont lancés dans le même dossier `output/`.

`--manifest` accepte aussi un dossier : `--manifest manifests/` exécute tous les `.yaml` qu'il contient à la suite (un couple audit/rapport par manifeste), avec les mêmes `--host`/`--dbnames`/etc. pour tous.

### 2. Régénérer le rapport (sans connexion, depuis un JSON existant)

Utile pour reproduire un rapport après coup (autre troncature `--max-rows`, JSON archivé d'un run précédent) :

```powershell
pgaudit-runner report `
  --input output/audit_20260612_143022.json `
  --output output/rapport_20260612.md
```

### 3. Convertir le rapport en HTML (optionnel)

Le rapport Markdown peut être relu, commenté et édité à la main avant conversion — la commande `html` prend un fichier `.md` en entrée, pas le JSON :

```powershell
pgaudit-runner html `
  --input output/rapport_20260612.md `
  --output output/rapport_20260612.html
```

Produit un fichier HTML autonome (CSS intégrée, aucune dépendance externe, aucun binaire à installer). Pour un PDF, ouvrir le fichier dans un navigateur et imprimer (Ctrl+P → Enregistrer en PDF).

### 4. Tableau de bord (agrège plusieurs runs)

Page HTML unique qui recense les bloquants/points de vigilance et les erreurs de collecte de **tous** les `audit_*.json` d'un dossier (plusieurs manifestes, plusieurs dates), avec un lien vers le rapport HTML complet de chaque run — celui-ci est régénéré à chaque appel :

```powershell
pgaudit-runner dashboard --input-dir output/
```

Produit `output/index.html` (nom personnalisable via `--output`, mais il doit rester dans `--input-dir` : les liens vers les rapports sont relatifs). Tant qu'aucune requête des manifestes n'expose `severite`/`constat` ou `expect_rows` (cf. Verdicts et synthèse, non calibré à ce jour), la section Bloquants affiche une note explicite plutôt qu'un tableau vide silencieux — la section Erreurs de collecte, elle, reflète toujours l'état réel.

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
| `--dry-run` | Simule sans connexion réelle (vérifie ce qui serait lancé) — `--host`/`--user`/`--output` deviennent optionnels (`output/` par défaut) |
| `--no-with-report` | Ne produit que le JSON, sans générer le rapport Markdown automatiquement |
| `--max-rows 200` | Seuil de troncature du rapport auto-généré (défaut : 100) |
| `--work-mem 256MB` | `SET work_mem` en début de session — utile pour les scans lourds (`data_quality_on_tables.yaml`) sur un serveur au réglage par défaut trop bas |
| `--quiet` | Supprime la progression en direct (`[12/30] id (base, source)... -> success`), affichée par défaut — utile en usage scripté |

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
    description: >              # optionnel, 2-4 lignes : à quoi sert ce contrôle
      Explique le rôle de cette requête dans le contexte du manifeste (ex. ce
      qu'elle bloque pour une migration PG14 → PG18, ou ce qu'elle révèle pour
      un audit qualité). Affiché dans le JSON (results[].description) et en
      citation dans le rapport Markdown/HTML.
    file: database/mon_check.sql
    scope: database             # "instance" ou "database"
    enabled: true
    tags: [schema]
    requires_superuser: false
    skip_reason_if_disabled: "Raison affichée si enabled: false"
    expect_rows: 0              # optionnel : nombre de lignes attendu
    severity_if_unexpected: bloquant  # optionnel (défaut vigilance) : bloquant | vigilance | info
```

### Synthèse (bloquants / vigilance)

Convention pour la détection des bloquants : **zéro ligne renvoyée = sain**. `--tags bloquant` donne un run rapide de type « est-ce que je peux y aller ».
Note : `shared_preload_libraries` est un inventaire (renvoie des lignes même quand tout va bien) ; `public_schema_create_acl` est une requête informative taguée `delta` ; voir `.tydata/specs/specs_detection_migration_1.md`.

Si au moins une requête déclare `expect_rows`, ou expose des colonnes `severite`/`constat` dans son résultat, le rapport affiche une section **Synthèse** en tête (avant le sommaire) : nombre de bloquants et points de vigilance, avec renvoi vers le détail. La convention de colonnes (`severite`/`constat`) prime sur `expect_rows` quand une requête a les deux — elle donne un message précis plutôt que générique.

**Tant qu'aucune requête n'utilise ce mécanisme, la section n'apparaît pas** — le rapport reste identique à avant, volontairement : afficher « aucun bloquant » sans avoir calibré une seule requête donnerait un faux sentiment de sécurité. Voir `.tydata/specs/specs_verdicts.md`.

---

## Sécurité

- `read_only: true` (défaut) : toute requête contenant `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT` ou `REVOKE` est rejetée avant exécution (garde-fou purement textuel).
- Le mot de passe n'apparaît jamais dans le JSON de sortie ni dans les logs.
- Recommandation : utiliser un rôle PostgreSQL en lecture seule côté serveur, en complément du garde-fou applicatif (néanmoins, certaines requêtes nécessitant un accès superuser seront bypassées).

## Limitations

- L'outil est conçu pour l'audit et la génération de rapports, pas pour exécuter des migrations. Il ne modifie jamais la base.
- Par exemple, il n'est pas possible de comparer la matrice de droits à une cible YAML et générer les `GRANT`/`REVOKE` correctifs — c'est volontairement hors scope de l'audit des droits car nature différente (comparaison + génération de code, pas lecture seule + rapport). Cela pourra éventuellement devenir un outil séparé une fois une matrice réelle validée.

---

## `qgisaudit-runner` — inventaire des projets QGIS (module séparé)

Outil **autonome**, distinct de `pgaudit-runner` : ne se connecte à aucune base, lit uniquement des fichiers `.qgs`/`.qgz` sur disque (partages réseau). Sa propre commande CLI (`qgisaudit-runner`), sa propre configuration YAML. Spec complète : `.tydata/specs/spec_script_inventaire_qgis.md`.

```powershell
cp qgisaudit_runner/config.example.yml config_qgis.yml
# éditer config_qgis.yml : racines à parcourir, dossier de sortie

qgisaudit-runner --config config_qgis.yml
```

Parcourt récursivement les racines déclarées, identifie les couches PostgreSQL de chaque projet (`<provider>postgres</provider>`), et classe chaque projet selon son mode de connexion (`nommee` = tout en `service=` centralisé, `embarquee` = tout en connexion directe/`authcfg=`, `mixte`, `sans_pg`). Produit deux CSV dans le dossier de sortie :

- `projets.csv` — une ligne par projet (comptage de couches, profil, drapeaux `mdp_en_clair`/`authcfg_utilise`, services/hôtes/bases distincts).
- `couches_pg.csv` — une ligne par couche PostgreSQL (mode de connexion, paramètres, schéma/table/colonne géométrique/SRID).

Pensé pour être croisé avec `role_membership_tree` de `rights_audit.json` (jointure sur le nom de rôle QGIS `user=`). Lecture seule, ne plante jamais sur un fichier corrompu (erreurs logguées sur stderr, traitement des autres fichiers poursuivi).
