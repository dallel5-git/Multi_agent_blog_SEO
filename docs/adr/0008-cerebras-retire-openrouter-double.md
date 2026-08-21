# ADR 0008 — Cerebras retiré, OpenRouter doublé (chaîne à 3 fournisseurs)

- **Statut :** accepté
- **Date :** 2026-08-21
- **Supersède partiellement :** ADR 0007 (Cerebras retiré de la chaîne)

## Contexte

L'ADR 0007 a mis en place une chaîne à 4 fournisseurs (Groq → OpenRouter →
Cerebras → Gemini) sans avoir pu vérifier Cerebras et OpenRouter de bout en
bout, faute de clés au moment de l'écriture. Les deux clés ont depuis été
fournies et testées :

- **Cerebras** : la clé authentifie, mais les deux modèles accessibles
  (`gpt-oss-120b`, `gemma-4-31b`) renvoient systématiquement HTTP 402
  « Payment required to access this resource » — ce compte exige une
  facturation activée pour l'inférence, malgré le free tier annoncé. C'est
  différent du blocage Gemini (ADR 0006) : là, le projet Google spécifique
  était suspendu (un accident de compte, potentiellement résolu ailleurs) ;
  ici, la nécessité d'une carte bancaire est une caractéristique du produit
  Cerebras pour ce type de compte, donc **contraire à la règle absolue de
  l'ADR 0003** (« aucun SDK ni appel vers un service payant, même en
  option »). Cerebras est donc retiré de la chaîne par défaut, pas seulement
  déprioritisé.
- **OpenRouter** : la clé fonctionne, mais le modèle par défaut choisi dans
  l'ADR 0007 (`meta-llama/llama-3.3-70b-instruct:free`) est lui aussi devenu
  payant entre-temps (HTTP 404, message de migration vers la version
  payante). Testé sur 3 modèles `:free` réellement disponibles au moment de
  l'écriture : `nvidia/nemotron-3-super-120b-a12b:free` répond correctement
  en texte simple et en JSON strict ; `openai/gpt-oss-20b:free` répond en
  texte simple mais a été rate-limité (HTTP 429) sur un appel JSON suivant
  immédiatement le premier ; `z-ai/glm-5.2:free` répond vite en texte simple
  mais renvoie un contenu vide en JSON strict.

## Décision

**La chaîne LLM par défaut devient Groq → OpenRouter → OpenRouter → Gemini**,
avec deux modèles OpenRouter distincts sous la même clé plutôt qu'un seul
fournisseur Cerebras retiré :
- `openrouter_model` = `nvidia/nemotron-3-super-120b-a12b:free` (vérifié
  texte + JSON) ;
- `openrouter_model_2` = `openai/gpt-oss-20b:free` (vérifié texte, secours
  si le premier est rate-limité ou momentanément payant).

`OpenRouterLLM.__init__` accepte désormais un paramètre `name` optionnel : les
deux instances utilisent `"openrouter"` et `"openrouter-2"` pour que
`FallbackLLM` (qui indexe son suivi de quota épuisé et ses statistiques
d'usage par `provider.name`) ne les confonde pas — sans ce paramètre, un 429
sur le premier modèle aurait aussi écarté le second pour le reste du run.

`CerebrasLLM` reste dans le code (`infrastructure/llm/cerebras.py`),
inchangé, pour quiconque dispose d'un compte Cerebras sans l'exigence de
facturation constatée ici.

## Conséquences

**Positives**
- Les deux modèles OpenRouter par défaut sont désormais vérifiés de bout en
  bout (texte simple et JSON strict), contrairement à l'état laissé par
  l'ADR 0007.
- La chaîne ne dépend plus d'un fournisseur qui exige une carte bancaire,
  respectant strictement l'ADR 0003.
- Deux maillons OpenRouter sous une seule clé absorbent le cas déjà observé
  deux fois pendant ces tests : un modèle `:free` qui devient payant ou
  rate-limité du jour au lendemain.

**Négatives**
- Les modèles `:free` d'OpenRouter changent visiblement plus vite que ceux
  de Groq/Gemini/Cerebras (deux ruptures constatées en une seule session de
  tests) : `OPENROUTER_MODEL`/`OPENROUTER_MODEL_2` sont plus susceptibles de
  se périmer que les autres valeurs par défaut du projet.
- Perte d'un fournisseur réellement distinct (infrastructure différente) :
  les deux maillons OpenRouter partagent la même clé et le même compte, donc
  une panne ou une suspension du compte OpenRouter éliminerait les deux à la
  fois — contrairement à la diversité initiale visée par l'ADR 0007.

## Vérification

```bash
blogseo check
# doit lister Groq, OpenRouter (x2, modèles différents), Gemini — plus de Cerebras

python -m pytest tests/unit/test_openrouter_llm.py tests/unit/test_llm_fallback.py \
                 tests/unit/test_container_offline.py -v
```
