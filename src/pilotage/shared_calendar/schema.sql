-- =============================================================================
--  Calendrier partagé — schéma SQLite
--
--  Une seule base, aucun serveur, aucun compte : la contrainte « 100 % gratuit,
--  jamais de carte bancaire » est respectée par construction.
--
--  Application :  sqlite3.Connection.executescript(open("schema.sql").read())
--  Rejouable    :  tout est en CREATE ... IF NOT EXISTS.
--
--  ⚠️  SQLite n'applique PAS les clés étrangères par défaut. Chaque connexion
--      doit exécuter `PRAGMA foreign_keys = ON;` — le PRAGMA ci-dessous ne vaut
--      que pour la session qui joue ce script.
--
--  Les valeurs de `platform` sont celles de `pilotage.platforms.Platform` :
--  youtube · tiktok · instagram · x · facebook · telegram_channel · blog
--  (`blog` est en lecture seule : ses lignes viennent du système `blogseo`.)
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- 1. content_items — une idée de contenu, quelle que soit la plateforme
--
--    Chaque pipeline crée SES propres lignes. Deux plateformes n'ont aucune
--    obligation de partager un sujet : l'indépendance éditoriale est la règle.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    topic           TEXT,                       -- sujet en une phrase
    body            TEXT,                       -- brouillon généré (script, légende, post…)
    status          TEXT    NOT NULL DEFAULT 'idea',
    -- Mention croisée SUGGÉRÉE vers un contenu déjà publié ailleurs.
    -- Toujours facultative, toujours validée à la main avant publication.
    cross_ref_id    INTEGER,
    cross_ref_state TEXT    NOT NULL DEFAULT 'none',
    scheduled_for   TEXT,                       -- date ISO souhaitée (indicative)
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT ck_content_platform CHECK (platform IN (
        'youtube', 'tiktok', 'instagram', 'x', 'facebook', 'telegram_channel', 'blog'
    )),
    CONSTRAINT ck_content_status CHECK (status IN (
        'idea', 'drafted', 'pending_review', 'approved', 'published', 'rejected', 'archived'
    )),
    CONSTRAINT ck_cross_ref_state CHECK (cross_ref_state IN (
        'none', 'suggested', 'accepted', 'declined'
    )),
    -- Un contenu ne peut pas se référencer lui-même.
    CONSTRAINT ck_cross_ref_not_self CHECK (cross_ref_id IS NULL OR cross_ref_id <> id),
    FOREIGN KEY (cross_ref_id) REFERENCES content_items (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_content_platform_status
    ON content_items (platform, status);
CREATE INDEX IF NOT EXISTS ix_content_scheduled
    ON content_items (scheduled_for);

-- -----------------------------------------------------------------------------
-- 2. platform_posts — une publication réelle, avec son lien
--
--    Créée quand l'auteur confirme la publication manuelle via `/publie [lien]`.
--    Un content_item peut donner plusieurs posts (republication, format court).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_item_id INTEGER NOT NULL,
    platform        TEXT    NOT NULL,
    url             TEXT    NOT NULL,
    -- Identifiant natif (video_id YouTube, media_id Instagram, message_id Telegram…).
    -- Indispensable au collecteur de statistiques : l'URL ne suffit pas toujours.
    external_id     TEXT,
    published_at    TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),

    CONSTRAINT ck_post_platform CHECK (platform IN (
        'youtube', 'tiktok', 'instagram', 'x', 'facebook', 'telegram_channel', 'blog'
    )),
    -- Un même lien ne doit pas être enregistré deux fois.
    CONSTRAINT uq_post_url UNIQUE (url),
    FOREIGN KEY (content_item_id) REFERENCES content_items (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_posts_platform_date
    ON platform_posts (platform, published_at);

-- -----------------------------------------------------------------------------
-- 3. stat_snapshots — une mesure d'audience à un instant t
--
--    Le tableau de bord trace des séries temporelles : on ACCUMULE les mesures,
--    on ne met jamais une ligne à jour.
--
--    `source` distingue mesure automatique (API) et mesure déclarée à la main
--    (X et TikTok n'ont pas d'API d'engagement gratuite).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stat_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_post_id  INTEGER,                  -- NULL = mesure au niveau du compte
    platform          TEXT    NOT NULL,
    captured_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    source            TEXT    NOT NULL DEFAULT 'api',

    views             INTEGER,
    likes             INTEGER,
    comments          INTEGER,
    shares            INTEGER,
    followers         INTEGER,                  -- mesure de compte (abonnés du canal…)
    -- Suivi des conversions, alimenté à la main ou par le paramètre de suivi
    -- des liens d'affiliation.
    affiliate_clicks  INTEGER,
    sales             INTEGER,
    revenue_tnd       REAL,

    CONSTRAINT ck_stat_platform CHECK (platform IN (
        'youtube', 'tiktok', 'instagram', 'x', 'facebook', 'telegram_channel', 'blog'
    )),
    CONSTRAINT ck_stat_source CHECK (source IN ('api', 'manual')),
    FOREIGN KEY (platform_post_id) REFERENCES platform_posts (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_stats_platform_date
    ON stat_snapshots (platform, captured_at);
CREATE INDEX IF NOT EXISTS ix_stats_post
    ON stat_snapshots (platform_post_id);

-- -----------------------------------------------------------------------------
-- Vue de confort : dernière mesure connue par publication.
-- Utilisée par le tableau de bord et par la commande /stats des bots.
-- -----------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_latest_stats AS
SELECT s.*
FROM stat_snapshots AS s
JOIN (
    SELECT platform_post_id, MAX(captured_at) AS captured_at
    FROM stat_snapshots
    WHERE platform_post_id IS NOT NULL
    GROUP BY platform_post_id
) AS last
  ON last.platform_post_id = s.platform_post_id
 AND last.captured_at      = s.captured_at;
