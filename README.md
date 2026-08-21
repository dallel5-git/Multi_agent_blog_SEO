# blogseo-agents

**Système multi-agents qui rédige, relit, optimise et publie un article de blog SEO tous les 2 jours — pour 0 dinar.**

Neuf agents orchestrés par LangGraph font la veille technologique mondiale et
tunisienne, choisissent un sujet non redondant, rédigent l'article en français,
vérifient son exactitude technique, optimisent son SEO, le passent au crible d'une
checklist de qualité, puis **vous demandent confirmation sur Telegram** avant
toute publication.

> 🇹🇳 Blog cible : https://oussama-ai-blog-v1.vercel.app/ — IA, automatisation,
> Make, n8n, Python et agents IA, pour un public tunisien.

---

## Sommaire

1. [Le principe en 30 secondes](#1-le-principe-en-30-secondes)
2. [Installation](#2-installation)
3. [Configuration des clés](#3-configuration-des-clés-gratuites)
4. [Premier lancement](#4-premier-lancement-sans-risque)
5. [Le bot Telegram](#5-le-bot-telegram--votre-bouton-de-publication)
6. [Automatiser tous les 2 jours](#6-automatiser-tous-les-2-jours)
7. [Toutes les commandes](#7-toutes-les-commandes)
8. [Architecture](#8-architecture)
9. [Coût](#9-coût--0-)
10. [Dépannage](#10-dépannage)

---

## 1. Le principe en 30 secondes

```
Hacker News ─┐
Reddit ──────┤
dev.to ──────┼──► 1. Trend Scout ──┐
RSS ─────────┘                     │
                                   ├──► 3. Keyword Analyst ──► 4. Content Writer
Recherche web TN ─┐                │        (anti-doublon)          │
Google Trends TN ─┼──► 2. Tunisia ─┘                                ▼
Médias TN (RSS) ──┘      Watcher                        5. Technical Reviewer
                                                                    ▼
                                                            6. SEO Editor
                                                                    ▼
                                              ┌──────────► 7. Quality Gate
                                              │  (rejet)          │ (OK)
                                              └───────────────────┤
                                                                  ▼
                                                          8. Publisher
                                                    ┌─────────────┴─────────────┐
                                                    │   📱 Telegram : 3 boutons  │
                                                    └─────────────┬─────────────┘
                                        ✅ push Git      ❌ local seul      🔁 réécrire
                                              │                │                 │
                                              └────────┬───────┘        (retour agent 4)
                                                       ▼
                                              9. Analytics Tracker
```

**Rien n'est publié sans votre clic.** Un brouillon est systématiquement écrit
dans `storage/drafts/`, même si Telegram ou Git tombent.

---

## 2. Installation

**Prérequis :** Python 3.10 ou plus (3.10.12 d'Ubuntu 22.04 convient), Git.

```bash
cd "/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/blog-seo-agents"

make install        # crée .venv, installe tout et le paquet en mode editable
```

Ou manuellement :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

> La première exécution télécharge le modèle d'embeddings `all-MiniLM-L6-v2`
> (~90 Mo, une seule fois). Il tourne ensuite entièrement en local sur CPU.

---

## 3. Configuration des clés (gratuites)

```bash
cp .env.example .env
nano .env
```

Il vous faut **au minimum une clé parmi les quatre ci-dessous** (Groq
recommandé, le plus fiable en pratique). Chaque clé supplémentaire allonge la
chaîne de secours automatique — voir [ADR 0007](docs/adr/0007-chaine-llm-a-quatre-fournisseurs.md).
Comptez 5 minutes par clé, aucune carte bancaire n'est demandée nulle part.

### 3.1 Groq — LLM en tête de chaîne (recommandé)

1. https://console.groq.com/keys → **Create API Key**

```env
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
```

### 3.2 OpenRouter, Cerebras, Gemini — fournisseurs de secours (optionnels)

Si le fournisseur précédent atteint son quota ou tombe en panne (HTTP 429 ou
5xx), le pipeline bascule automatiquement au suivant dans l'ordre Groq →
OpenRouter → Cerebras → Gemini. Renseignez-en autant que vous voulez :

```env
OPENROUTER_API_KEY=...    # https://openrouter.ai/keys
CEREBRAS_API_KEY=...      # https://cloud.cerebras.ai (Platform → API Keys)
GEMINI_API_KEY=...        # https://aistudio.google.com/apikey
```

Voir `.env.example` pour le détail de chaque fournisseur (modèle par défaut,
quotas, particularités observées — ex. certains comptes Cerebras exigent une
facturation activée même en free tier).

### 3.3 Telegram — votre télécommande de publication (recommandé)

1. Sur Telegram, cherchez **@BotFather** → `/newbot` → suivez les instructions
   → vous recevez un token du type `123456789:AAF...`
2. **Envoyez un message quelconque à votre nouveau bot** (indispensable : un bot
   ne peut pas écrire le premier).
3. Ouvrez dans un navigateur :
   `https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates`
4. Repérez `"chat":{"id":123456789` → c'est votre `TELEGRAM_CHAT_ID`.

```env
TELEGRAM_BOT_TOKEN=123456789:AAF...
TELEGRAM_CHAT_ID=123456789
```

### 3.4 Chemins de votre blog

Déjà pré-remplis pour votre machine — vérifiez qu'ils correspondent :

```env
BLOG_CONTENT_DIR=/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog/content/articles
BLOG_REPO_DIR=/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog
```

### 3.5 Tavily — optionnel

Repli de recherche si DuckDuckGo bloque. 1000 requêtes/mois gratuites sur
https://tavily.com. Laissez vide si vous n'en voulez pas.

---

## 4. Premier lancement (sans risque)

### Étape 1 — vérifier la configuration

```bash
make check
```

Affiche ce qui est configuré, ce qui manque, et le nombre d'articles détectés
dans votre blog.

### Étape 2 — un run complet SANS clé ni réseau

```bash
make offline
```

Utilise un LLM factice. Aucun appel réseau, aucune clé consommée. Cela valide que
toute la mécanique fonctionne : les 9 agents, la boucle de feedback, l'écriture
du `.mdx`. **Faites-le en premier.**

### Étape 3 — un vrai run, mais sans publier

```bash
make dry-run
```

Vrais LLM, vraie veille, vrai article — mais **rien n'est écrit dans le blog et
rien n'est poussé sur Git**. Le résultat est dans `storage/drafts/`.

Pour lire l'article directement dans le terminal :

```bash
blogseo run --dry-run --print
```

**Faites tourner `--dry-run` plusieurs fois** et relisez les brouillons avant de
passer au mode réel.

### Étape 4 — le vrai run

```bash
make run
```

Le pipeline s'exécute puis vous envoie l'article sur Telegram avec les trois
boutons. Il attend votre décision jusqu'à 24 h.

---

## 5. Le bot Telegram : votre bouton de publication

Vous recevez un message avec le titre, la meta description, le slug, la catégorie,
le nombre de mots, le score de qualité, un extrait — et le `.mdx` complet en
pièce jointe.

| Bouton | Ce qui se passe exactement |
|---|---|
| ✅ **Publier (push Git)** | Le `.mdx` est écrit dans `content/articles/`, l'image de couverture est copiée dans `public/covers/`, puis `git add` + `commit` + `push` sur `main`. **Vercel déploie tout seul dans la minute.** |
| ❌ **Garder en local** | Le `.mdx` est écrit dans `content/articles/` **et c'est tout**. Aucun commit, aucun push. Vous relisez, vous corrigez, et vous poussez vous-même. |
| 🔁 **Faire réécrire** | L'article repart au Content Writer avec un feedback. Rien n'est écrit dans le blog. |

### Après un ❌, pour publier vous-même

```bash
cd "/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog"
# relisez / corrigez content/articles/<slug>.mdx
npm run build          # optionnel : vérifier que le build passe
git add content/articles/<slug>.mdx public/covers/<slug>.jpg
git commit -m "content: <titre de l'article>"
git push
```

### Si vous ne répondez pas

Au bout de 24 h (`TELEGRAM_REVIEW_TIMEOUT_S`), le comportement de ❌ s'applique :
le fichier est écrit en local, rien n'est poussé. C'est le choix sûr.

---

## 6. Automatiser tous les 2 jours

### Pourquoi en local et pas sur GitHub Actions ?

Parce que le bouton ❌ doit écrire **sur votre disque**. Un runner GitHub Actions
tourne dans un conteneur jetable dans le cloud : il n'a aucun accès à
`/home/oussama/...`. Le pipeline doit donc s'exécuter là où vivent vos fichiers.

### Option A — au premier plan (pour tester)

```bash
make scheduler
# ou, pour déclencher un premier run tout de suite :
python -m blogseo.interfaces.scheduler --now
```

### Option B — service systemd (recommandé)

```bash
./scripts/install_systemd_timer.sh
```

Le script installe un service utilisateur et un timer qui se déclenche toutes les
48 h, survit au redémarrage, et écrit ses logs dans `journalctl`.

```bash
systemctl --user status  blogseo.timer     # état
systemctl --user list-timers blogseo.timer # prochaine exécution
journalctl --user -u blogseo.service -f    # logs en direct
systemctl --user stop    blogseo.timer     # mettre en pause
```

> `loginctl enable-linger $USER` (fait par le script) permet au timer de tourner
> même quand vous n'êtes pas connecté en session graphique.

---

## 7. Toutes les commandes

| Commande | Description |
|---|---|
| `blogseo check` | Vérifie la configuration, les clés et les dépendances |
| `blogseo run` | Run complet avec validation Telegram |
| `blogseo run --dry-run` | Run complet sans écrire dans le blog ni pousser |
| `blogseo run --offline` | Run complet sans réseau ni clé (LLM factice) |
| `blogseo run --print` | Affiche l'article final dans le terminal |
| `blogseo run --no-human-review` | Publie sans demander (⚠️ déconseillé) |
| `blogseo run --orchestrator sequential` | Force l'exécuteur séquentiel |
| `blogseo index` | Réindexe les articles existants pour l'anti-doublon |
| `blogseo graph` | Affiche le diagramme Mermaid du pipeline |
| `blogseo runs` | Liste les derniers runs |
| `blogseo show <run_id>` | Détaille un run étape par étape |

Équivalents `make` : `check`, `offline`, `dry-run`, `run`, `index`, `graph`,
`runs`, `scheduler`, `test`, `lint`.

---

## 8. Architecture

```
src/blogseo/
├── domain/                  ← ne dépend de RIEN
│   ├── entities/            Article, Topic, TrendItem, ReviewResult, PipelineRun
│   ├── value_objects/       Slug, Category, SeoMetadata, QualityReport
│   ├── ports/               LLMPort, SearchPort, ArticleHistoryPort, NotifierPort…
│   └── errors.py
│
├── application/             ← ne dépend que des ports
│   ├── agents/              les 9 agents
│   ├── prompts/             prompts système, documentés en français
│   ├── dto/                 PipelineState (l'objet qui circule entre agents)
│   └── use_cases/           GenerateArticleUseCase
│
├── infrastructure/          ← implémente les ports
│   ├── llm/                 groq.py, openrouter.py, cerebras.py, gemini.py, fallback_chain.py, fake.py
│   ├── search/              duckduckgo.py, tavily.py, composite.py
│   ├── sources/             hackernews.py, reddit.py, devto.py, rss.py
│   ├── trends/              pytrends_adapter.py
│   ├── embeddings/          sentence_transformers_adapter.py
│   ├── vectorstore/         chroma_history.py
│   ├── images/              pollinations.py
│   ├── publishing/          mdx_writer.py, git_publisher.py
│   ├── notifications/       telegram.py
│   ├── persistence/         mdx_article_source.py, json_run_repository.py
│   ├── analytics/           stub.py
│   └── config/              settings.py, container.py, logging_config.py
│
├── orchestrator/            pipeline_spec.py, graph.py (LangGraph), sequential.py
├── interfaces/              cli.py, scheduler.py
└── shared/                  rate_limiter.py, retry.py, json_utils.py, text.py
```

**Règle de dépendance :** les flèches ne pointent que vers l'intérieur.
`domain/` n'importe jamais `infrastructure/`.

Documentation détaillée : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
décisions techniques : [`docs/adr/`](docs/adr/),
contexte et pièges : [`MEMOIRE.md`](MEMOIRE.md).

### Ajouter un agent

1. Créer `application/agents/mon_agent.py` héritant de `Agent`.
2. L'ajouter au `AgentBundle` et à `ordered()` dans `orchestrator/pipeline_spec.py`.
3. Mettre à jour `LINEAR_EDGES`.
4. L'instancier dans `infrastructure/config/container.py`.

Aucun autre fichier à toucher.

---

## 9. Coût : 0 €

| Service | Free tier | Carte bancaire ? |
|---|---|---|
| Groq | ~30 req/min | ❌ non |
| OpenRouter (`:free`) | limité mais suffisant en secours | ❌ non |
| Cerebras | free tier (facturation parfois requise selon le compte) | ❌ non |
| Google Gemini | ~15 req/min, ~1500/jour | ❌ non |
| DuckDuckGo (`ddgs`) | illimité en pratique | ❌ aucune inscription |
| Google Trends (`pytrends`) | gratuit | ❌ aucune inscription |
| Hacker News / Reddit / dev.to | API publiques | ❌ aucune inscription |
| sentence-transformers + ChromaDB | 100 % local | ❌ aucune inscription |
| Pollinations.ai | gratuit | ❌ aucune inscription |
| Telegram Bot API | gratuit | ❌ non |
| Vercel (blog existant) | Hobby | ❌ non |

**Consommation par run :** 7 à 9 appels LLM en cas nominal (jusqu'à 13 avec deux
révisions) — largement sous les quotas gratuits de la chaîne pour un run
toutes les 48 h.

Aucun SDK ni appel vers un service payant n'est présent dans le code — ni en
option, ni en commentaire.

---

## 10. Dépannage

**`blogseo: command not found`**
→ `source .venv/bin/activate`, ou utilisez `python -m blogseo.interfaces.cli`.

**« Aucune clé LLM configurée »**
→ Le pipeline bascule sur le LLM factice et produit un article d'exemple.
Renseignez au moins une clé (`GROQ_API_KEY` recommandée) dans `.env`.

**« Telegram inactif »**
→ `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` manquants. Sans eux, les articles sont
écrits en local sans être poussés (comportement de ❌).

**Le bot ne reçoit pas mes clics**
→ Vérifiez que vous avez bien envoyé un premier message au bot. Vérifiez aussi
qu'aucun autre process n'appelle `getUpdates` en parallèle : Telegram ne délivre
un update qu'à un seul consommateur.

**« Push refusé »**
→ Le commit est créé localement, rien n'est perdu. Configurez vos identifiants
Git (`gh auth login` ou une clé SSH) puis `git push` manuellement.

**« ChromaDB indisponible »**
→ Repli automatique sur un index JSON. Le pipeline fonctionne, l'anti-doublon est
juste moins fin. `pip install chromadb` pour le mode complet.

**Le sujet est rejeté pour doublon à chaque tentative**
→ Votre blog couvre déjà beaucoup de terrain sur ce thème. Baissez
`DUPLICATE_THRESHOLD` (0.90 par exemple) ou élargissez les sources de veille.

**Quota d'un fournisseur LLM épuisé**
→ La bascule vers le suivant de la chaîne (Groq → OpenRouter → Cerebras →
Gemini) est automatique. Vérifiez dans les logs :
`[chaîne LLM] <fournisseur> a atteint son quota → bascule`.

**DuckDuckGo renvoie 0 résultat**
→ Augmentez `SEARCH_DELAY_S` à 4 ou 5, ou ajoutez une clé Tavily.

---

## Licence

MIT — Oussama Dallel.

## Liens

- 📺 [YouTube](https://www.youtube.com/@oussamadallel5)
- 💼 [LinkedIn](https://www.linkedin.com/in/oussama-dallel-120143209/)
- 💻 [GitHub](https://github.com/dallel5-git)
