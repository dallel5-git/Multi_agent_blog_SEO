# MEMOIRE.md — mémoire du projet

> **À lire en premier par tout agent IA ou développeur qui reprend ce projet.**
> Ce fichier contient le contexte, les décisions déjà prises et les pièges connus.
> Il évite de re-poser des questions déjà tranchées et de refaire des erreurs déjà faites.
>
> **Règle de maintenance :** toute décision structurante ajoutée au projet doit
> être consignée ici *le jour même*, avec sa date et sa raison.

---

## 1. Identité du projet

| | |
|---|---|
| **Nom** | `blogseo-agents` |
| **Objet** | Générer automatiquement, tous les 2 jours, un article de blog optimisé SEO |
| **Propriétaire** | Oussama Dallel |
| **Dépôt** | https://github.com/dallel5-git/Multi_agent_blog_SEO |
| **Emplacement local** | `/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/blog-seo-agents` |
| **Blog cible** | https://oussama-ai-blog-v1.vercel.app/ (Next.js 14, App Router) |
| **Dépôt du blog** | `/home/oussama/Bureau/Chaine_youtube_Oussama_Dallel/Blog IA/oussama-blog` |
| **Langue du contenu** | Français |
| **Audience** | Tunisie : étudiants, PME/petits business, professionnels IT, développeurs |
| **Version** | 1.0.0 |
| **Dernière mise à jour** | 2026-08-19 |

---

## 2. Contrainte n°1 : budget zéro, sans exception

**Le projet ne doit JAMAIS nécessiter une carte bancaire.** Cette contrainte est
non négociable et prime sur toute considération de performance ou d'élégance.

### Stack imposée (toutes en free tier permanent)

| Besoin | Service retenu | Clé requise | Quota gratuit |
|---|---|---|---|
| LLM principal | **Cerebras** (`llama-3.3-70b`) — [ADR 0006](docs/adr/0006-cerebras-remplace-gemini.md), remplace Gemini | oui, gratuite | voir docs fournisseur |
| LLM de secours | **Groq** (`openai/gpt-oss-20b`) | oui, gratuite | ~30 req/min |
| Recherche web | **DuckDuckGo** (`ddgs`) | **aucune** | non déclaré |
| Recherche (repli) | **Tavily** | optionnelle | 1000 req/mois |
| Tendances | **pytrends** (Google Trends) | **aucune** | non déclaré |
| Veille tech | HN Firebase API, Reddit `.json`, dev.to API, RSS | **aucune** | publiques |
| Embeddings | **sentence-transformers** `all-MiniLM-L6-v2` | **aucune** | local, CPU |
| Vector store | **ChromaDB** (SQLite embarqué) | **aucune** | local |
| Image de couverture | **Pollinations.ai** | **aucune** | non déclaré |
| Notifications | **Telegram Bot API** | oui, gratuite | illimité |
| Planification | **APScheduler** local | **aucune** | — |

### Interdictions absolues

- ❌ Aucun SDK ni appel vers **OpenAI**, **Anthropic**, **Pinecone**, **SerpAPI payant**.
- ❌ Pas même en commentaire « à activer plus tard ».
- ❌ Aucune dépendance qui exige une carte bancaire pour s'inscrire.

> Si vous ajoutez une dépendance, vérifiez d'abord son free tier **permanent**
> (un essai de 14 jours ne compte pas) et documentez-le dans le tableau ci-dessus.

---

## 3. Contrainte n°2 : la règle de publication (décidée par l'auteur)

C'est **la** règle métier du projet. Elle est implémentée dans
`application/agents/publisher.py` et couverte par
`tests/unit/test_publisher_decision.py`.

Le pipeline **ne publie jamais sans confirmation humaine explicite**. À la fin du
run, un message Telegram avec trois boutons est envoyé :

| Bouton | Effet exact |
|---|---|
| ✅ **Publier** | `.mdx` écrit dans `content/articles/` → `git add` + `commit` + `push` → **Vercel déploie automatiquement** |
| ❌ **Garder en local** | `.mdx` écrit dans `content/articles/` **et rien d'autre**. Aucun commit, aucun push. L'auteur relit et pousse lui-même. |
| 🔁 **Faire réécrire** | Retour au Content Writer avec un feedback. **Rien n'est écrit dans le blog.** |

**Cas particuliers :**

- Aucune réponse dans le délai (24 h par défaut) → comportement de ❌ (`TELEGRAM_DEFAULT_ON_TIMEOUT=reject`). Le choix sûr est de ne pas publier.
- Telegram non configuré → comportement de ❌.
- `HUMAN_REVIEW=false` → publication automatique. **À n'activer qu'après plusieurs semaines de dry-runs concluants.**
- `--dry-run` → seul le brouillon `storage/drafts/` est écrit. Le dossier du blog n'est jamais touché.

**Dans tous les cas, un brouillon est écrit dans `storage/drafts/` avant toute
décision.** Le travail du pipeline n'est jamais perdu, même si Telegram tombe,
même si Git refuse le push.

---

## 4. Le blog cible : ce qu'il faut absolument savoir

Le blog Next.js existait **avant** ce projet. Le pipeline doit s'y conformer,
jamais l'inverse.

### Format des articles

Les articles sont des fichiers **`.mdx`** (pas `.md`) dans
`oussama-blog/content/articles/`. Le nom du fichier **est** le slug de l'URL :
`mon-article.mdx` → `/blog/mon-article`.

Frontmatter attendu (miroir exact de `src/types/article.ts`) :

```yaml
---
title: "..."             # string, obligatoire
description: "..."       # string, obligatoire — sert de meta description
date: "2026-08-19"       # string ISO, obligatoire
category: "n8n"          # UNION FERMÉE, voir ci-dessous
tags: ["n8n", "ia"]      # string[]
coverImage: ""           # string, optionnel — chemin relatif à public/
youtubeUrl: ""           # string, optionnel
author: "Oussama Dallel" # string, optionnel
featured: false          # boolean, optionnel
---
```

### ⚠️ Piège n°1 : la catégorie est une union TypeScript fermée

```ts
export type Category = "IA" | "n8n" | "Make" | "Python" | "Agents IA";
```

**Toute autre valeur casse le build Next.js.** C'est pourquoi
`domain/value_objects/category.py` normalise systématiquement la sortie du LLM
(`Category.coerce()`), avec des alias pour les erreurs fréquentes (`N8N`,
`agents ia`, `integromat`…) et un repli sur `IA`.

### ⚠️ Piège n°2 : pas de H1 dans le corps

Le composant `ArticleHeader.tsx` affiche déjà le `title` du frontmatter. Un `# `
dans le corps produirait deux H1 → pénalité SEO. Le Content Writer a la consigne,
le Quality Gate le vérifie (contrôle `pas_de_h1`, bloquant), et le Content Writer
dégrade automatiquement tout H1 résiduel en H2.

### ⚠️ Piège n°3 : composants MDX disponibles

Le blog rend nativement `<Callout type="info|warning">` et `<YoutubeEmbed>`
(déclarés dans `src/components/MDXComponents.tsx`). **Inventer un autre composant
fait échouer le build.** Le prompt du Content Writer liste explicitement les
composants autorisés.

### ⚠️ Piège n°4 : versions figées de l'écosystème unified

Le `package.json` du blog fige `remark-gfm`, `rehype-pretty-code` et
`rehype-autolink-headings` sur des versions compatibles `next-mdx-remote` v4.
**Ne lancez pas `npm update` dans le blog** sans vérifier que le build passe.

### ⚠️ Piège n°5 : un `#` dans un bloc de code n'est pas un titre

Un commentaire Python `# ...` à l'intérieur d'un bloc ``` était initialement
détecté comme un H1 par `Article.headings`, ce qui bloquait à tort le Quality
Gate. Corrigé le 2026-08-19 : les blocs de code sont neutralisés avant toute
analyse de structure, de longueur ou de densité de mots-clés.

---

## 5. Architecture retenue : Clean Architecture

```
interfaces/       CLI, planificateur          ← dépend de tout
      ↓
orchestrator/     graphe LangGraph
      ↓
application/      agents, cas d'usage, prompts ← dépend UNIQUEMENT des ports
      ↓
domain/           entités, value objects, PORTS ← ne dépend de RIEN
      ↑
infrastructure/   adapters (Cerebras, Groq, DDG, Chroma, Telegram, Git…)
```

**Règle de dépendance : les flèches ne pointent que vers l'intérieur.**
`domain/` n'importe jamais `infrastructure/`. Vérifiable d'une commande :

```bash
grep -r "infrastructure" src/blogseo/domain/   # doit ne rien renvoyer
```

Le câblage se fait dans un seul fichier : `infrastructure/config/container.py`
(*composition root*). Changer de LLM, de moteur de recherche ou de canal de
notification = modifier ce fichier uniquement.

### Pourquoi ce découpage

1. Le Quality Gate est testable sans réseau (aucun appel LLM dedans, volontairement).
2. Le mode `--offline` remplace juste `LLMPort` par `FakeLLM` : tout le pipeline
   tourne sans clé ni connexion.
3. Brancher Search Console plus tard = un nouvel adapter de `AnalyticsPort`,
   zéro ligne modifiée dans les agents.

---

## 6. Les 9 agents

| # | Agent | Rôle | LLM ? | Critique ? |
|---|---|---|---|---|
| 1 | **Trend Scout** | Veille tech mondiale (HN, Reddit, dev.to, RSS) | oui (synthèse) | non |
| 2 | **Tunisia Watcher** | Veille tunisienne (recherche web, RSS, Trends TN) | oui (structuration) | non |
| 3 | **Keyword Analyst** | Choisit LE sujet + mots-clés + plan, **vérifie l'anti-doublon** | oui | **oui** |
| 4 | **Content Writer** | Rédige le corps en Markdown (1200-2000 mots) | oui | **oui** |
| 5 | **Technical Reviewer** | Vérifie code, faits, liens (HTTP réel), secrets | oui + déterministe | non |
| 6 | **SEO Editor** | meta title/description, slug, alt-text, maillage interne | oui + validation déterministe | **oui** |
| 7 | **Quality Gate** | Checklist de validation | **NON, 100 % déterministe** | **oui** |
| 8 | **Publisher** | Couverture, validation Telegram, écriture, Git | non | **oui** |
| 9 | **Analytics Tracker** | Réindexation anti-doublon + feedback perf (stub) | non | non |

« Non critique » = une exception de cet agent est journalisée puis avalée ; le
pipeline continue en mode dégradé. Une veille morte ne doit pas empêcher
d'écrire un article.

### Deux boucles de feedback

1. **Quality Gate → Content Writer** : si un contrôle bloquant échoue, l'article
   repart en révision avec des consignes précises. Borné par `MAX_REVISIONS` (2).
   Au-delà, l'article part quand même en validation humaine avec ses défauts
   affichés — mieux vaut une décision humaine informée qu'un run perdu.
2. **Publisher (bouton 🔁) → Content Writer** : réécriture demandée manuellement.

---

## 7. Anti-doublon : comment ça marche

1. Au démarrage de chaque run, tous les `.mdx` de `content/articles/` sont lus et
   réindexés (l'auteur a pu en ajouter un à la main entre deux runs).
2. Chaque article est encodé en vecteur : `titre + description + catégorie + tags`.
3. Le Keyword Analyst encode son sujet candidat et interroge l'index.
4. Si la similarité cosinus du plus proche voisin **≥ `DUPLICATE_THRESHOLD` (0.85)**,
   le sujet est rejeté et le LLM doit en proposer un autre (jusqu'à 3 tentatives,
   avec une température croissante pour sortir de l'ornière).
5. Après écriture réussie, l'Analytics Tracker ajoute le nouvel article à l'index.

**Repli :** si `sentence-transformers` ou `chromadb` sont absents, le système
bascule sur un encodeur par hachage de n-grammes et un index JSON. Moins fin
sémantiquement, mais le pipeline reste fonctionnel — et les tests tournent en CI
sans télécharger 90 Mo de modèle.

---

## 8. Gestion des quotas gratuits

- **Rate limiter à double fenêtre** (`shared/rate_limiter.py`) : bloque *avant*
  l'appel plutôt que d'encaisser un 429. L'état journalier est persisté sur disque,
  donc redémarrer le process ne remet pas le compteur à zéro.
- **Bascule Gemini → Groq** (`infrastructure/llm/fallback_chain.py`) :
  - `QuotaExceededError` (429) → bascule immédiate **et** le fournisseur est
    écarté pour le reste du run ;
  - `LLMError` (réseau, 5xx) → bascule, mais on retentera le fournisseur au
    prochain appel ;
  - tous en échec → `AllProvidersFailedError`, le run échoue proprement et une
    notification Telegram part.
- **Retry avec backoff exponentiel + jitter** sur tous les appels réseau.
- **Consommation observée par run** : ~7 à 9 appels LLM en cas nominal, jusqu'à
  ~13 avec deux révisions. Très largement sous le quota Gemini gratuit
  (1500/jour) pour un run toutes les 48 h.

---

## 9. Décisions prises et pourquoi (résumé des ADR)

| Date | Décision | Raison courte |
|---|---|---|
| 2026-08-19 | Clean Architecture en 4 couches | Testabilité, mode offline, remplacement d'adapters sans toucher aux agents |
| 2026-08-19 | LangGraph **+ exécuteur séquentiel de secours** | Les boucles conditionnelles sont déclaratives ; le repli garantit que l'absence de LangGraph ne bloque rien |
| 2026-08-19 | **APScheduler local**, pas GitHub Actions | Le bouton ❌ doit écrire sur **le disque de l'auteur** ; un runner cloud n'y a pas accès |
| 2026-08-19 | Quality Gate **sans LLM** | Reproductible, testable, impossible à « charmer » par un modèle |
| 2026-08-19 | Telegram en **REST brut** (`requests`) | Pas d'`asyncio`, pas de `python-telegram-bot`, long-polling simple à raisonner |
| 2026-08-19 | Publication Git **fichier par fichier** (jamais `git add -A`) | Ne jamais emporter le travail en cours de l'auteur dans un commit du bot |
| 2026-08-19 | Écriture `.mdx` **atomique** (tmp + `os.replace`) | Next.js ne doit jamais lire un fichier à moitié écrit |
| 2026-08-19 | Maillage interne en **section « À lire aussi »** en fin d'article | Insérer des liens au milieu du texte généré casse trop souvent le sens |
| 2026-08-19 | Mot-clé considéré présent si **tous ses mots** le sont | Évite les titres artificiels du type « Automatiser prospection n8n : … » |

Le détail complet est dans `docs/adr/`.

---

## 10. Pièges déjà rencontrés (ne pas les refaire)

1. **Dataclass `slots=True` + valeur par défaut** : `MaClasse.mon_champ` renvoie
   le descripteur de slot, **pas** la valeur par défaut. Les chemins par défaut du
   blog sont donc des constantes de module (`DEFAULT_BLOG_CONTENT_DIR`).
2. **LangGraph avec `StateGraph(dict)`** : tout passe par un canal racine
   `__root__` en `LastValue`, qui refuse deux écritures dans un même pas et fait
   échouer `draw_mermaid()`. Il faut un **`TypedDict`** avec une clé nommée.
3. **DuckDuckGo bannit les appels rapprochés** : un délai de 2 s entre requêtes
   est imposé (`SEARCH_DELAY_S`).
4. **Reddit exige un User-Agent explicite**, sinon 429 systématique.
5. **Google Trends (pytrends) tombe régulièrement en 429** : traité comme un
   signal optionnel, jamais bloquant.
6. **Les LLM gratuits enrobent le JSON** de texte, de fences et de virgules
   finales : `shared/json_utils.extract_json()` encaisse tout ça.
7. **Le nom du paquet DuckDuckGo a changé** (`duckduckgo-search` → `ddgs`) :
   l'adapter tente les deux imports.
8. **Collision de slug** : si le fichier existe déjà, on suffixe par la date
   plutôt que d'écraser un article publié.

---

## 11. Commandes utiles

```bash
make install          # installation complète dans .venv
make check            # vérifie la configuration et les dépendances
make offline          # run complet SANS clé API ni réseau  ← à faire en premier
make dry-run          # run complet avec vrais LLM, sans rien publier
make run              # run complet avec validation Telegram
make test             # tests unitaires
make graph            # diagramme Mermaid du pipeline
make scheduler        # démarre la planification toutes les 48 h
blogseo runs          # historique des runs
blogseo show <run_id> # détail d'un run
```

---

## 12. État d'avancement

### Fait (v1.0.0)

- [x] Clean Architecture 4 couches, règle de dépendance respectée
- [x] 9 agents avec prompts système documentés en français
- [x] Orchestration LangGraph + repli séquentiel, 2 boucles de feedback
- [x] Bascule Gemini → Groq + rate limiter double fenêtre persisté
- [x] Anti-doublon sémantique ChromaDB + repli JSON
- [x] Validation humaine Telegram à 3 boutons
- [x] Publication Git conditionnelle (✅ push / ❌ local)
- [x] Génération de couverture Pollinations + image de secours Pillow
- [x] Mode `--dry-run` et mode `--offline`
- [x] Planificateur local 48 h + unité systemd
- [x] 125 tests unitaires (Quality Gate, anti-doublon, SEO, fallback LLM, routage, Publisher)
- [x] CLI complète (`run`, `check`, `index`, `graph`, `runs`, `show`)

### À faire (backlog GitHub)

- [ ] Brancher Google Search Console sur `AnalyticsPort` (l'interface est prête)
- [ ] Ajouter des flux RSS de médias tech tunisiens dans `TUNISIA_RSS_FEEDS`
- [ ] Génération automatique d'un post LinkedIn/X à partir de l'article
- [ ] Tableau de bord HTML local des runs
- [ ] Mode « série » : plusieurs articles liés entre eux

Voir `docs/BACKLOG.md` et les issues du dépôt.

---

## 13. Contacts et liens

- Chaîne YouTube : https://www.youtube.com/@oussamadallel5
- LinkedIn : https://www.linkedin.com/in/oussama-dallel-120143209/
- GitHub : https://github.com/dallel5-git
- Clé Cerebras gratuite : https://cloud.cerebras.ai
- Clé Groq gratuite : https://console.groq.com/keys
- Créer un bot Telegram : parler à `@BotFather` sur Telegram
