"""Verrouillage de l'ossature du paquet `pilotage` (lot 0 — cadrage).

Le squelette ne contient volontairement aucune logique métier : il n'y a donc
rien à tester au sens habituel. Ce que ces tests protègent, ce sont les
**décisions d'architecture** prises pendant le cadrage, celles qu'une session
de développement ultérieure pourrait défaire sans s'en apercevoir :

1. l'isolation stricte entre `pilotage` et `blogseo` (aucun import croisé) ;
2. la présence d'un pipeline ET d'un bot pour chacune des 6 plateformes ;
3. la cohérence entre l'énum `Platform`, les contraintes `CHECK` du schéma SQL
   et les variables déclarées dans `.env.example` ;
4. le fait que `schema.sql` s'applique réellement à une base SQLite ;
5. la structure du Brand Kernel, et le fait que ses valeurs non décidées
   restent des `TODO` explicites plutôt que des valeurs inventées.

Voir `CADRAGE.md`, risque n°7 (« dérive du squelette »).
"""

from __future__ import annotations

import ast
import re
import sqlite3
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML est une dépendance déclarée du projet")

from pilotage.platforms import Platform  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PILOTAGE_DIR = PROJECT_ROOT / "src" / "pilotage"
BLOGSEO_DIR = PROJECT_ROOT / "src" / "blogseo"
SCHEMA_SQL = PILOTAGE_DIR / "shared_calendar" / "schema.sql"
BRAND_KERNEL_YAML = PILOTAGE_DIR / "brand_kernel" / "brand_kernel.yaml"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

#: Modules attendus dans chaque dossier de plateforme.
PIPELINE_MODULES = ("__init__.py", "watcher.py", "writer.py", "spec.py")
BOT_MODULES = ("__init__.py", "handlers.py")


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(path: Path) -> set[str]:
    """Paquets racine réellement importés par un fichier (docstrings exclus)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


# --------------------------------------------------------------------------- #
# 1. Énumération des plateformes
# --------------------------------------------------------------------------- #
def test_platform_compte_six_plateformes_pilotees_plus_le_blog():
    assert len(Platform) == 7
    assert len(Platform.piloted()) == 6
    assert Platform.BLOG not in Platform.piloted()


def test_platform_est_serialisable_en_chaine():
    """Les valeurs partent telles quelles en base et dans les callback_data
    Telegram : `str(...)`/comparaison directe doivent fonctionner."""
    assert Platform.YOUTUBE == "youtube"
    assert Platform("tiktok") is Platform.TIKTOK


def test_chaque_plateforme_a_un_libelle_lisible():
    for platform in Platform:
        assert platform.label
        assert platform.label != platform.value or platform is Platform.X


# --------------------------------------------------------------------------- #
# 2. Arborescence : un pipeline et un bot par plateforme pilotée
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("platform", Platform.piloted(), ids=lambda p: p.value)
def test_chaque_plateforme_pilotee_a_son_pipeline(platform: Platform):
    directory = PILOTAGE_DIR / "pipelines" / platform.value
    assert directory.is_dir(), f"pipeline manquant pour {platform.value}"
    for module in PIPELINE_MODULES:
        assert (directory / module).is_file(), f"{platform.value}/{module} manquant"


@pytest.mark.parametrize("platform", Platform.piloted(), ids=lambda p: p.value)
def test_chaque_plateforme_pilotee_a_son_bot(platform: Platform):
    directory = PILOTAGE_DIR / "bots" / platform.value
    assert directory.is_dir(), f"bot manquant pour {platform.value}"
    for module in BOT_MODULES:
        assert (directory / module).is_file(), f"{platform.value}/{module} manquant"


def test_le_blog_na_pas_de_pipeline_ni_de_bot():
    """Le blog est produit par `blogseo` : il n'apparaît dans le calendrier
    qu'en lecture, jamais comme pipeline du pilotage."""
    assert not (PILOTAGE_DIR / "pipelines" / "blog").exists()
    assert not (PILOTAGE_DIR / "bots" / "blog").exists()


def test_les_modules_structurants_existent():
    attendus = [
        "platforms.py",
        "brand_kernel/loader.py",
        "brand_kernel/schema.py",
        "shared_calendar/schema.sql",
        "shared_calendar/migrate.py",
        "shared_calendar/models.py",
        "shared_calendar/repository.py",
        "pipelines/base.py",
        "bots/base.py",
        "stats_collector/base.py",
        "stats_collector/youtube_api.py",
        "stats_collector/meta_graph.py",
        "stats_collector/telegram_api.py",
        "stats_collector/manual_entry.py",
        "dashboard/app.py",
        "dashboard/views/kanban.py",
        "dashboard/views/stats.py",
        "dashboard/views/conversions.py",
        "config/settings.py",
    ]
    manquants = [chemin for chemin in attendus if not (PILOTAGE_DIR / chemin).is_file()]
    assert not manquants, f"fichiers de squelette manquants : {manquants}"


# --------------------------------------------------------------------------- #
# 3. Isolation stricte entre les deux paquets  (ARCHITECTURE.md §1)
# --------------------------------------------------------------------------- #
def test_pilotage_nimporte_jamais_blogseo():
    coupables = [
        str(f.relative_to(PROJECT_ROOT))
        for f in _python_files(PILOTAGE_DIR)
        if "blogseo" in _imported_roots(f)
    ]
    assert not coupables, (
        "`pilotage` ne doit jamais importer `blogseo` : le pilotage ne doit pas "
        f"casser quand le blog évolue. Fichiers fautifs : {coupables}"
    )


def test_blogseo_nimporte_jamais_pilotage():
    coupables = [
        str(f.relative_to(PROJECT_ROOT))
        for f in _python_files(BLOGSEO_DIR)
        if "pilotage" in _imported_roots(f)
    ]
    assert not coupables, (
        "`blogseo` ne doit jamais importer `pilotage` : le pipeline blog doit "
        f"tourner même si le pilotage n'existe pas. Fichiers fautifs : {coupables}"
    )


# --------------------------------------------------------------------------- #
# 4. Le squelette est du Python valide et documenté
# --------------------------------------------------------------------------- #
def test_tous_les_modules_sont_du_python_valide():
    for fichier in _python_files(PILOTAGE_DIR):
        try:
            ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        except SyntaxError as exc:  # pragma: no cover - message de diagnostic
            pytest.fail(f"{fichier.relative_to(PROJECT_ROOT)} : {exc}")


def test_chaque_module_du_squelette_explique_son_role():
    """Un squelette sans docstring est un squelette illisible dans trois mois."""
    muets = [
        str(f.relative_to(PROJECT_ROOT))
        for f in _python_files(PILOTAGE_DIR)
        if not ast.get_docstring(ast.parse(f.read_text(encoding="utf-8")))
    ]
    assert not muets, f"modules sans docstring : {muets}"


# --------------------------------------------------------------------------- #
# 5. Schéma SQL du calendrier partagé
# --------------------------------------------------------------------------- #
@pytest.fixture
def db() -> sqlite3.Connection:
    """Base en mémoire, schéma appliqué, clés étrangères activées."""
    connexion = sqlite3.connect(":memory:")
    connexion.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


def _colonnes(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def test_le_schema_sapplique_sur_une_base_vierge(db: sqlite3.Connection):
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"content_items", "platform_posts", "stat_snapshots"} <= tables


def test_le_schema_est_rejouable(db: sqlite3.Connection):
    """`CREATE ... IF NOT EXISTS` partout : une migration relancée ne casse rien."""
    db.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))


def test_les_trois_tables_ont_leurs_colonnes_cles(db: sqlite3.Connection):
    assert {"platform", "title", "body", "status", "cross_ref_id", "cross_ref_state"} <= _colonnes(
        db, "content_items"
    )
    assert {"content_item_id", "url", "external_id", "published_at"} <= _colonnes(
        db, "platform_posts"
    )
    assert {"platform_post_id", "captured_at", "source", "views", "affiliate_clicks",
            "revenue_tnd"} <= _colonnes(db, "stat_snapshots")


@pytest.mark.parametrize("platform", list(Platform), ids=lambda p: p.value)
def test_le_schema_accepte_toutes_les_valeurs_de_lenum(db: sqlite3.Connection, platform: Platform):
    """La contrainte CHECK et l'énum `Platform` doivent rester synchronisées."""
    db.execute(
        "INSERT INTO content_items (platform, title) VALUES (?, ?)",
        (platform.value, "Test"),
    )


def test_le_schema_refuse_une_plateforme_inconnue(db: sqlite3.Connection):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO content_items (platform, title) VALUES ('mastodon', 'Test')")


def test_le_schema_refuse_un_statut_inconnu(db: sqlite3.Connection):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO content_items (platform, title, status) VALUES ('x', 'T', 'peut-etre')"
        )


def test_un_contenu_ne_peut_pas_se_mentionner_lui_meme(db: sqlite3.Connection):
    db.execute("INSERT INTO content_items (platform, title) VALUES ('youtube', 'A')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE content_items SET cross_ref_id = id WHERE id = 1")


def test_un_meme_lien_ne_peut_pas_etre_enregistre_deux_fois(db: sqlite3.Connection):
    db.execute("INSERT INTO content_items (platform, title) VALUES ('youtube', 'A')")
    insert = (
        "INSERT INTO platform_posts (content_item_id, platform, url, published_at) "
        "VALUES (1, 'youtube', 'https://youtu.be/abc', '2026-08-23')"
    )
    db.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(insert)


def test_supprimer_un_contenu_supprime_ses_publications_et_ses_mesures(db: sqlite3.Connection):
    db.execute("INSERT INTO content_items (platform, title) VALUES ('youtube', 'A')")
    db.execute(
        "INSERT INTO platform_posts (content_item_id, platform, url, published_at) "
        "VALUES (1, 'youtube', 'https://youtu.be/abc', '2026-08-23')"
    )
    db.execute("INSERT INTO stat_snapshots (platform_post_id, platform, views) VALUES (1, 'youtube', 10)")

    db.execute("DELETE FROM content_items WHERE id = 1")

    assert db.execute("SELECT COUNT(*) FROM platform_posts").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM stat_snapshots").fetchone()[0] == 0


def test_les_mesures_saccumulent_et_la_vue_renvoie_la_plus_recente(db: sqlite3.Connection):
    """`stat_snapshots` trace une courbe : on ajoute, on n'écrase jamais."""
    db.execute("INSERT INTO content_items (platform, title) VALUES ('youtube', 'A')")
    db.execute(
        "INSERT INTO platform_posts (content_item_id, platform, url, published_at) "
        "VALUES (1, 'youtube', 'https://youtu.be/abc', '2026-08-20')"
    )
    for jour, vues in (("2026-08-21", 100), ("2026-08-22", 250), ("2026-08-23", 400)):
        db.execute(
            "INSERT INTO stat_snapshots (platform_post_id, platform, captured_at, views) "
            "VALUES (1, 'youtube', ?, ?)",
            (jour, vues),
        )

    assert db.execute("SELECT COUNT(*) FROM stat_snapshots").fetchone()[0] == 3
    assert db.execute("SELECT views FROM v_latest_stats").fetchone()[0] == 400


def test_une_mesure_est_soit_api_soit_manuelle(db: sqlite3.Connection):
    """X et TikTok remontent en `manual` : le tableau de bord doit pouvoir les
    distinguer d'une mesure d'API."""
    db.execute("INSERT INTO stat_snapshots (platform, source, views) VALUES ('tiktok', 'manual', 5)")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO stat_snapshots (platform, source) VALUES ('x', 'devine')")


# --------------------------------------------------------------------------- #
# 6. Brand Kernel
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def kernel() -> dict:
    return yaml.safe_load(BRAND_KERNEL_YAML.read_text(encoding="utf-8"))


def test_le_brand_kernel_est_un_yaml_valide(kernel: dict):
    assert isinstance(kernel, dict)
    assert kernel["version"] == 1


def test_le_brand_kernel_declare_ses_cinq_sections(kernel: dict):
    assert {"identity", "voice", "visual", "audience", "offers"} <= set(kernel)


def test_le_brand_kernel_porte_les_valeurs_fournies_par_lauteur(kernel: dict):
    assert kernel["identity"]["slogan"] == "Prenez le contrôle de votre temps grâce à l'IA"
    assert kernel["identity"]["language"] == "fr"
    assert kernel["audience"]["country"] == "Tunisie"


def test_le_brand_kernel_couvre_les_champs_attendus(kernel: dict):
    assert {"tone", "address", "forbidden", "emoji_policy"} <= set(kernel["voice"])
    assert {"primary", "secondary", "accent", "background", "text"} <= set(kernel["visual"]["colors"])
    assert {"heading", "body"} <= set(kernel["visual"]["fonts"])
    for offre in kernel["offers"]:
        assert {"id", "name", "url", "active", "call_to_action"} <= set(offre)


def test_une_offre_active_a_toujours_un_lien_reel(kernel: dict):
    """Une offre n'est citée par un rédacteur que si l'auteur l'a activée
    explicitement, une fois le lien d'affiliation réel renseigné — une offre
    active sans lien serait un contenu publié cassé sur six plateformes.
    Validé à nouveau par `load_brand_kernel()`, voir `test_brand_kernel.py`."""
    for offre in kernel["offers"]:
        if offre["active"]:
            assert offre["url"], f"offre active sans lien : {offre['id']}"


# --------------------------------------------------------------------------- #
# 7. Variables d'environnement déclarées
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def env_example() -> str:
    return ENV_EXAMPLE.read_text(encoding="utf-8")


@pytest.mark.parametrize("platform", Platform.piloted(), ids=lambda p: p.value)
def test_chaque_bot_de_pilotage_a_son_token_et_son_chat_id(env_example: str, platform: Platform):
    prefixe = f"PILOTAGE_{platform.value.upper()}"
    assert f"{prefixe}_BOT_TOKEN=" in env_example
    assert f"{prefixe}_CHAT_ID=" in env_example


def test_les_cles_de_statistiques_sont_declarees(env_example: str):
    for variable in (
        "YOUTUBE_API_KEY",
        "YOUTUBE_CHANNEL_ID",
        "META_PAGE_ACCESS_TOKEN",
        "META_PAGE_ID",
        "META_INSTAGRAM_BUSINESS_ID",
        "TELEGRAM_CHANNEL_USERNAME",
        "PILOTAGE_DB_PATH",
        "BRAND_KERNEL_PATH",
    ):
        assert f"{variable}=" in env_example, f"{variable} absente de .env.example"


def test_le_bot_du_blog_reste_distinct_des_bots_de_pilotage(env_example: str):
    """Risque n°5 du cadrage : ne jamais confondre le bot de validation des
    articles avec les six bots de pilotage."""
    assert re.search(r"^TELEGRAM_BOT_TOKEN=", env_example, re.MULTILINE)
    assert "PILOTAGE_TELEGRAM_CHANNEL_BOT_TOKEN=" in env_example


def test_env_example_ne_contient_aucune_valeur_de_cle(env_example: str):
    """Règle absolue du projet : `.env.example` documente, il ne divulgue pas."""
    motifs_de_cle = re.compile(r"(AIza[\w-]{10,}|gsk_[\w]{10,}|sk-[\w]{10,}|\d{9,}:AA[\w-]{20,})")
    assert not motifs_de_cle.search(env_example)


# --------------------------------------------------------------------------- #
# 8. Documents de cadrage
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nom", ["ARCHITECTURE.md", "CADRAGE.md"])
def test_les_documents_de_cadrage_existent(nom: str):
    fichier = PROJECT_ROOT / nom
    assert fichier.is_file()
    assert len(fichier.read_text(encoding="utf-8")) > 2_000


def test_larchitecture_du_blog_existante_na_pas_ete_ecrasee():
    """`ARCHITECTURE.md` (racine, multi-plateformes) et `docs/ARCHITECTURE.md`
    (pipeline blog) sont deux documents distincts."""
    assert (PROJECT_ROOT / "docs" / "ARCHITECTURE.md").is_file()


# --------------------------------------------------------------------------- #
# 9. Cohérence du backlog GitHub
#
#    `scripts/create_github_issues.sh` crée labels, milestones puis issues.
#    Un label ou un milestone absent ne se voit qu'au milieu de la création,
#    une fois quarante issues déjà poussées. Autant le détecter ici.
# --------------------------------------------------------------------------- #
GITHUB_DIR = PROJECT_ROOT / "scripts" / "github"


def _charge(nom: str):
    import json

    return json.loads((GITHUB_DIR / nom).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def backlog() -> tuple[set[str], set[str], list[dict]]:
    labels = {entree["name"] for entree in _charge("labels.json")}
    milestones = {entree["title"] for entree in _charge("milestones.json")}
    return labels, milestones, _charge("issues.json")


def test_chaque_issue_utilise_des_labels_declares(backlog):
    labels, _, issues = backlog
    inconnus = sorted({nom for issue in issues for nom in issue["labels"] if nom not in labels})
    assert not inconnus, f"labels absents de labels.json : {inconnus}"


def test_chaque_issue_pointe_vers_un_milestone_declare(backlog):
    _, milestones, issues = backlog
    inconnus = sorted({i["milestone"] for i in issues if i["milestone"] not in milestones})
    assert not inconnus, f"milestones absents de milestones.json : {inconnus}"


def test_aucun_titre_dissue_en_double(backlog):
    """Le script saute les titres déjà présents sur GitHub : deux issues
    homonymes dans le JSON signifient qu'une seule serait créée."""
    _, _, issues = backlog
    titres = [i["title"] for i in issues]
    doublons = sorted({t for t in titres if titres.count(t) > 1})
    assert not doublons, f"titres en double : {doublons}"


def test_chaque_issue_a_un_corps_et_des_criteres_dacceptation(backlog):
    _, _, issues = backlog
    incompletes = [
        i["title"] for i in issues
        if not i["body"].strip() or "Critères d'acceptation" not in i["body"]
    ]
    assert not incompletes, f"issues sans critères d'acceptation : {incompletes}"


def test_chaque_lot_du_pilotage_a_son_epic(backlog):
    _, _, issues = backlog
    lots = {m for m in (i["milestone"] for i in issues) if m.startswith("Lot ")}
    avec_epic = {i["milestone"] for i in issues if "epic" in i["labels"]}
    orphelins = sorted(lots - avec_epic)
    assert not orphelins, f"lots sans issue epic de synthèse : {orphelins}"
