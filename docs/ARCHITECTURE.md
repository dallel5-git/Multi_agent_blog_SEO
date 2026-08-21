# Architecture

## 1. Vue d'ensemble

Le système applique une **Clean Architecture** à quatre couches, avec une règle
de dépendance stricte : **les dépendances ne pointent que vers l'intérieur**.

```
┌─────────────────────────────────────────────────────────────────────┐
│  interfaces/            CLI, planificateur APScheduler              │
│  ↓ dépend de tout                                                   │
├─────────────────────────────────────────────────────────────────────┤
│  orchestrator/          graphe LangGraph, exécuteur séquentiel      │
│  ↓ dépend de application/ et domain/                                │
├─────────────────────────────────────────────────────────────────────┤
│  application/           les 9 agents, prompts, cas d'usage          │
│  ↓ dépend UNIQUEMENT des ports du domain                            │
├─────────────────────────────────────────────────────────────────────┤
│  domain/                entités, value objects, PORTS, erreurs      │
│  ↑ ne dépend de RIEN (ni framework, ni requests, ni chemin disque)  │
├─────────────────────────────────────────────────────────────────────┤
│  infrastructure/        adapters : Groq, OpenRouter, Gemini,        │
│                         DuckDuckGo,                                 │
│                         Chroma, Telegram, Git, Pollinations…        │
│  ↑ implémente les ports du domain                                   │
└─────────────────────────────────────────────────────────────────────┘
                    ↕
     infrastructure/config/container.py  ← composition root : le SEUL
                                            endroit où tout se rencontre
```

### Vérifier la règle de dépendance

```bash
grep -rn "infrastructure" src/blogseo/domain/      # doit ne rien renvoyer
grep -rn "infrastructure" src/blogseo/application/ # doit ne rien renvoyer
```

---

## 2. Le domain

### Entités

| Entité | Rôle |
|---|---|
| `Article` | Le livrable. Connaît le format `.mdx` du blog, ignore où il sera écrit. |
| `Topic` | Le sujet retenu : titre, angle tunisien, mots-clés, plan, score d'originalité. |
| `TrendItem` / `TrendDigest` | Un signal de veille normalisé, quelle que soit sa source. |
| `ReviewResult` / `ReviewFinding` | Verdict du relecteur technique. |
| `PipelineRun` / `StepTrace` | Trace persistée d'une exécution. Agrégat racine. |

### Value objects (immuables)

| VO | Invariant garanti |
|---|---|
| `Slug` | ASCII, minuscules, tirets, sans mot vide, tronqué sur une frontière de mot. |
| `Category` | Appartient obligatoirement à l'union fermée du blog. |
| `SeoMetadata` | Sait dire si le titre/la description sont hors des bornes Google. |
| `QualityReport` | Agrège les contrôles, calcule le verdict et les consignes de révision. |

### Ports (interfaces abstraites)

```
LLMPort              generate(), generate_json(), is_available()
SearchPort           search(), search_news()
TrendsPort           interest_over_time(), related_queries()
TechSourcePort       fetch()
EmbeddingPort        embed()
ArticleHistoryPort   index(), find_similar(), count()
ArticleSourcePort    list_published(), slugs()
RunRepositoryPort    save(), get(), list_awaiting_review()
ArticleWriterPort    write()
GitPublisherPort     commit_and_push(), is_clean()
ImageGeneratorPort   generate()
NotifierPort         send(), send_document()
HumanReviewPort      request_decision(), acknowledge()
AnalyticsPort        fetch_performance(), build_feedback()
```

Chaque port a **au moins deux implémentations** (une réelle, une de test ou de
repli), ce qui valide qu'il est bien une abstraction et pas un moulage de
l'implémentation.

---

## 3. Le pipeline des 10 agents

### Contrat commun

Tout agent hérite de `application/agents/base.Agent` :

```python
class Agent(ABC):
    name: str        # identifiant du nœud dans le graphe
    label: str       # libellé lisible
    critical: bool   # False = une exception est journalisée puis avalée

    def run(self, state: PipelineState) -> PipelineState: ...
```

`__call__` enveloppe `run()` : chronométrage, trace dans le `PipelineRun`,
journalisation, et décision « je propage l'exception ou je dégrade ».

**Aucun agent n'en connaît un autre.** Ils communiquent uniquement par le
`PipelineState`. C'est ce qui rend l'ajout/retrait d'agent trivial.

### Tableau des agents

| # | Agent | Entrées (état) | Sorties (état) | LLM | Critique |
|---|---|---|---|---|---|
| 1 | Trend Scout | `existing_articles` | `global_digest`, `global_themes` | oui | non |
| 2 | Tunisia Watcher | — | `tunisia_digest`, `tunisia_context`, `trends_scores` | oui | non |
| 3 | Keyword Analyst | 1, 2, `performance_feedback` | `topic` | oui | **oui** |
| 4 | Content Writer | `topic`, `revision_instructions` | `article` | oui | **oui** |
| 5 | Technical Reviewer | `article` | `review` | oui + HTTP | non |
| 6 | SEO Editor | `article`, `topic` | `article.seo`, `article.slug` | oui | **oui** |
| 7 | Quality Gate | `article`, `review`, `topic` | `quality`, `revision_instructions` | **non** | **oui** |
| 8 | Publisher | `article`, `quality` | `draft_path`, `published_path`, `commit_sha` | non | **oui** |
| 9 | Social Writer | `article`, `run.status` | `linkedin_post`, `x_thread` | oui | non |
| 10 | Analytics Tracker | `article`, `run.status` | `performance_feedback` | non | non |

### Les deux boucles de feedback

```
                    ┌──────────────────────────────────────┐
                    │                                      │
   keyword_analyst ─┴─► content_writer ─► technical_reviewer ─► seo_editor
                          ▲    ▲                                   │
                          │    │                                   ▼
                          │    └──── (rejet, < MAX_REVISIONS) ── quality_gate
                          │                                        │ (OK)
                          │                                        ▼
                          └──────────── (bouton 🔁) ──────────  publisher
                                                                   │
                                                                   ▼
                                                            social_writer
                                                                   │
                                                                   ▼
                                                          analytics_tracker
```

Ces deux arêtes conditionnelles sont déclarées dans
`orchestrator/pipeline_spec.py` (`route_after_quality_gate`,
`route_after_publisher`) et consommées à l'identique par les deux exécuteurs.

**Bornage :**
- boucle Quality Gate : `MAX_REVISIONS` (2 par défaut) ; au-delà, l'article part
  quand même en validation humaine avec ses défauts affichés ;
- boucle 🔁 : `MAX_REVISIONS + 2` ;
- garde-fou global : `MAX_NODE_VISITS = 40` dans l'exécuteur séquentiel,
  `recursion_limit = 40` côté LangGraph.

### Mode série (issue #41)

Une invocation normale du pipeline produit un article isolé. Le mode série
permet de planifier 3 à 5 articles liés autour d'un même thème, publiés un par
un au fil des runs normaux (`blogseo run`, y compris via le scheduler 48h),
sans toucher à la topologie du graphe :

```
blogseo series start "<thème>" --size 4
        │
        ▼
KeywordAnalystAgent.plan_series()  ── 1 appel LLM pour N sujets
        │                              + anti-doublon (ArticleHistoryPort)
        ▼
storage/series/<id>.json  (ArticleSeries : N SeriesTopic, statut pending)
        │
        │  chaque `blogseo run` suivant :
        ▼
KeywordAnalystAgent.run()  ── consomme le 1er sujet "pending" de la série
        │                      active (aucun appel LLM), anti-doublon revérifié
        ▼
   ... pipeline normal (content_writer → ... → publisher) ...
        │
        ▼
PublisherAgent  ── à l'écriture dans le blog : statut → "written" (empêche
        │           la file de reservir ce sujet, même en dry-run/REJECT)
        │
        │  seulement si push Git réel (décision ✅) :
        ▼
   statut → "published" + réouverture des .mdx des épisodes précédents pour
   y injecter un lien vers ce nouvel article (section `## Cette série`,
   idempotente, distincte du « À lire aussi » du SEO Editor)
```

Chaque `SeriesTopic` suit son propre statut (`pending → written → published`,
ou `skipped` si un sujet planifié s'avère être un doublon au moment d'être
consommé) — voir [`domain/entities/series.py`](../src/blogseo/domain/entities/series.py).
Le maillage retour vit dans
[`shared/series_linking.py`](../src/blogseo/shared/series_linking.py) (rendu
pur, testable sans I/O) et son adaptateur
[`infrastructure/publishing/series_linker.py`](../src/blogseo/infrastructure/publishing/series_linker.py)
(port `SeriesBacklinkPort`).

---

## 4. Le Quality Gate en détail

**Aucun appel LLM.** C'est un choix structurant : la porte de qualité doit être
reproductible, testable unitairement et impossible à « charmer » par un modèle.

| Contrôle | Gravité | Ce qu'il vérifie |
|---|---|---|
| `longueur_minimale` | 🔴 bloquant | ≥ 1200 mots (hors code) |
| `longueur_maximale` | 🟡 avertissement | ≤ 2000 mots + 15 % de tolérance |
| `sections_h2` | 🔴 bloquant | ≥ 4 sections `##` |
| `pas_de_h1` | 🔴 bloquant | aucun `# ` dans le corps |
| `blocs_de_code_equilibres` | 🔴 bloquant | nombre pair de ``` |
| `presence_code_ou_liste` | 🟡 avertissement | au moins un exemple concret |
| `mot_cle_dans_le_corps` | 🔴 bloquant | mot-clé principal présent |
| `densite_mot_cle` | 🟡 avertissement | ≤ 2,5 % (anti-bourrage) |
| `mot_cle_dans_un_titre` | 🟡 avertissement | repris dans au moins une section |
| `angle_tunisien_present` | 🔴 bloquant | ≥ 2 occurrences de termes locaux |
| `angle_tunisien_en_intro` | 🟡 avertissement | présent dans les 1200 premiers caractères |
| `meta_description_presente` | 🔴 bloquant | non vide |
| `meta_title_longueur` | 🟡 avertissement | 30-60 caractères |
| `meta_description_longueur` | 🟡 avertissement | 120-158 caractères |
| `originalite_sujet` | 🔴 bloquant | similarité < `DUPLICATE_THRESHOLD` |
| `relecture_technique` | 🔴 bloquant | aucun finding bloquant |
| `liens_valides` | 🟡 avertissement | aucun lien mort |
| `appel_a_action` | 🟡 avertissement | CTA YouTube présent |

Un rejet produit `revision_instructions`, un texte structuré `[BLOQUANT]` /
`[À améliorer]` directement injecté dans le prompt de révision du Content Writer.

---

## 5. Résilience et modes dégradés

| Panne | Comportement |
|---|---|
| Un fournisseur LLM renvoie 429 | Bascule immédiate sur le suivant de la chaîne, ce fournisseur écarté pour le run |
| Un fournisseur LLM renvoie 500 / timeout | Bascule sur le suivant, ce fournisseur retenté au prochain appel |
| Les 4 fournisseurs LLM en échec | `AllProvidersFailedError`, run en échec + notification Telegram |
| Une source de veille morte | Journalisée, ignorée, les autres sources suffisent |
| Toutes les sources mortes | Avertissement ; le Keyword Analyst travaille avec ce qu'il a |
| DuckDuckGo bloque | Repli Tavily si la clé existe, sinon veille dégradée |
| Google Trends en 429 | Signal ignoré, jamais bloquant |
| `chromadb` absent | Repli sur un index JSON local |
| `sentence-transformers` absent | Repli sur un encodeur par hachage de n-grammes |
| `langgraph` absent | Repli sur l'exécuteur séquentiel, comportement identique |
| Pollinations indisponible | Image de secours générée localement avec Pillow |
| Pillow absent | Article publié sans couverture |
| Telegram indisponible | Décision par défaut = écriture locale seule |
| `git push` refusé | Commit local conservé, fichier écrit, message d'erreur explicite |
| Slug déjà pris | Suffixé par la date, jamais d'écrasement |

**Invariant :** un brouillon est écrit dans `storage/drafts/` avant toute
décision. Le travail du pipeline n'est jamais perdu.

---

## 6. Sécurité

- **Aucune clé en dur.** Tout passe par des variables d'environnement.
  `.env` est dans `.gitignore`.
- `Settings.describe()` n'affiche jamais une clé, seulement « configurée » /
  « absente ».
- Le Technical Reviewer **détecte les secrets en clair** dans l'article généré
  (motifs Google `AIza…`, OpenAI `sk-…`, Groq `gsk_…`, GitHub `ghp_…`, bot
  Telegram, Slack) et bloque la publication.
- Le Publisher ne commite **que les fichiers qu'il a produits** — jamais
  `git add -A` — pour ne pas emporter le travail en cours de l'auteur.
- L'identité Git du bot est posée en **configuration locale au dépôt**, pas en
  configuration globale.
- L'écriture du `.mdx` est **atomique** (fichier temporaire + `os.replace`) :
  Next.js ne peut jamais lire un fichier à moitié écrit.

---

## 7. Persistance

```
storage/
├── drafts/          brouillons .mdx (écrits à chaque run, même en dry-run)
├── runs/            un JSON par run : statut, étapes, décision, chemins
├── series/          un JSON par série d'articles liés (mode série, issue #41)
├── chroma/          base vectorielle SQLite (ou fallback_index.json)
├── covers/          images générées
├── logs/            pipeline.log, rotatif 2 Mo × 5
├── rate_limits/     quotas journaliers persistés (groq.json, openrouter.json, openrouter-2.json, gemini.json)
├── analytics/       performance.json (export Search Console manuel, optionnel)
└── telegram_offset.json   offset getUpdates, évite de rejouer un vieux callback
```

Aucune base de données à installer. Tout est lisible à l'œil nu pour le débogage.

---

## 8. Points d'extension prévus

| Extension | Ce qu'il y a à faire |
|---|---|
| Brancher Search Console | Nouvel adapter de `AnalyticsPort` + câblage dans le container |
| Changer de LLM | Nouvelle classe implémentant `LLMPort`, ajoutée à la chaîne |
| Notifier sur Slack/Discord | Nouvel adapter de `NotifierPort` + `HumanReviewPort` |
| Publier vers un CMS | Nouvel adapter de `ArticleWriterPort` / `GitPublisherPort` |
| Ajouter un 11ᵉ agent | Sous-classe de `Agent` + entrée dans `AgentBundle` + arête (le Social Writer, agent 9, en est l'exemple concret) |
| Publier sur plusieurs blogs | Paramétrer `blog_content_dir` par profil de configuration |

Dans la plupart des cas, **aucune modification des agents existants n'est
requise.** Exception notable : le mode série (issue #41) étend
`KeywordAnalystAgent` et `PublisherAgent` eux-mêmes (nouveaux paramètres
optionnels, rétrocompatibles) plutôt que d'ajouter un agent — la file
d'attente et le maillage retour ne peuvent pas exister en dehors du cycle de
vie de ces deux agents précis.
