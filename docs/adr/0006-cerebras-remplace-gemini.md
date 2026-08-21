# ADR 0006 — Cerebras remplace Gemini comme LLM principal

- **Statut :** accepté
- **Date :** 2026-08-21
- **Supersède partiellement :** ADR 0003 (ligne « LLM principal »)
- **Complétée par :** [ADR 0007](0007-chaine-llm-a-quatre-fournisseurs.md) — Gemini réintégré comme 4ᵉ maillon d'une chaîne de secours, Cerebras n'est plus seul « après Groq »

## Contexte

En validant les critères d'acceptation de l'issue #38 avec de vraies clés
d'API, les deux fournisseurs configurés par défaut se sont révélés
inutilisables tels quels :

- `gemini-2.0-flash` et plusieurs remplacements testés (`gemini-2.5-flash`,
  `gemini-flash-latest`) renvoient tous HTTP 403 « Your project has been
  denied access » avec la clé testée — un blocage au niveau du projet Google
  Cloud, indépendant du modèle choisi ;
- `llama-3.3-70b-versatile` (Groq) n'existe plus (HTTP 404) — corrigé
  séparément en basculant sur `openai/gpt-oss-20b`, toujours chez Groq.

Le blocage Gemini n'est pas un problème de configuration côté projet : c'est
la clé/le projet Google qui est en cause, hors du contrôle du code. Plutôt que
de dépendre d'un unique fournisseur « principal » sujet à ce genre de
suspension, le choix a été fait de changer de fournisseur principal.

## Décision

**Cerebras devient le fournisseur LLM principal, Groq reste le fournisseur de
secours.** Gemini est retiré de la chaîne par défaut construite dans
`Container.llm` (`infrastructure/config/container.py`), mais l'adapter
`GeminiLLM` (`infrastructure/llm/gemini.py`) reste dans le code, inchangé :
toute personne souhaitant le recâbler n'a qu'à l'ajouter à la liste
`providers` de `Container.llm`, sans toucher au domain ni aux agents (le
port `LLMPort` ne change pas).

`CerebrasLLM` (`infrastructure/llm/cerebras.py`) suit exactement le même
patron que `GroqLLM` : appel REST direct à une API compatible OpenAI, aucun
SDK, `json_mode` supporté, gestion du 429 en `QuotaExceededError` pour la
bascule automatique.

Cerebras a été retenu parmi les alternatives gratuites (Cerebras, OpenRouter
`:free`) par choix explicite de l'auteur — inférence très rapide (matériel
dédié WSE), free tier sans carte bancaire, API compatible OpenAI comme Groq.

## Conséquences

**Positives**
- La chaîne LLM ne dépend plus d'un projet Gemini spécifique dont l'état
  (actif/suspendu) échappe au contrôle du dépôt.
- `CerebrasLLM` vérifié de bout en bout n'a pas pu se faire faute de clé
  Cerebras au moment de l'écriture : seul le format de requête/réponse
  (identique à Groq, API OpenAI-compatible documentée) a été suivi. **À
  vérifier avec une vraie clé avant un run de production.**
- Groq (`openai/gpt-oss-20b`), lui, est vérifié de bout en bout (génération
  simple et JSON strict).

**Négatives**
- Les modèles et quotas gratuits changent avec le temps chez tous ces
  fournisseurs (déjà observé deux fois en une semaine sur ce projet) : les
  valeurs par défaut du code sont un point de départ, pas une garantie
  durable. `.env.example` renvoie vers les pages de tarification à jour de
  chaque fournisseur plutôt que d'y dupliquer des chiffres.
- `GeminiLLM` devient du code non exercé par défaut (aucun test ne le couvre
  spécifiquement) ; il reste néanmoins un adapter `LLMPort` complet et
  fonctionnel pour qui veut le réactiver.

## Vérification

```bash
grep -n "cerebras_api_key\|CEREBRAS_API_KEY" src/blogseo/infrastructure/config/container.py .env.example
# la chaîne LLM par défaut doit construire CerebrasLLM avant GroqLLM
blogseo check   # doit afficher « LLM principal : Cerebras (...) »
```
