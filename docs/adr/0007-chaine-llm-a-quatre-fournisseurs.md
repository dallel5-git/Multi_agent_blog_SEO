# ADR 0007 — Chaîne LLM à 4 fournisseurs (Groq → OpenRouter → Cerebras → Gemini)

- **Statut :** accepté
- **Date :** 2026-08-21
- **Complète :** ADR 0006 (Cerebras remplace Gemini)

## Contexte

L'ADR 0006 a remplacé Gemini par Cerebras comme fournisseur principal, suite
au blocage du projet Google associé à la clé testée. En testant ensuite une
vraie clé Cerebras (fournie par l'auteur), un second fournisseur « gratuit »
s'est révélé indisponible : tous les modèles accessibles avec cette clé
(`gpt-oss-120b`, `gemma-4-31b`) renvoient HTTP 402 « Payment required to
access this resource » — ce compte Cerebras exige apparemment une
facturation activée pour l'inférence, malgré le free tier annoncé.

À ce stade, sur 2 fournisseurs « gratuits » testés avec de vraies clés (hors
Groq), aucun ne fonctionnait tel quel (Gemini : projet bloqué ; Cerebras :
facturation requise). Conclusion de l'auteur : ne plus dépendre d'un seul
« fournisseur principal », mais construire une chaîne de secours plus longue
pour maximiser les chances qu'au moins un fournisseur réponde à chaque appel.

## Décision

**La chaîne LLM comporte 4 fournisseurs, essayés dans cet ordre : Groq →
OpenRouter → Cerebras → Gemini.** Seuls ceux dont la clé est configurée dans
`.env` entrent dans la chaîne (`Container.llm`,
`infrastructure/config/container.py`) ; l'ordre est fixe, pas de logique de
santé/priorité dynamique — chaque fournisseur en échec (429, 5xx, réseau)
fait basculer immédiatement au suivant (`FallbackLLM`, inchangé depuis ADR
0003).

L'ordre reflète l'état observé au moment de l'écriture, pas un jugement de
qualité :
1. **Groq** — seul fournisseur vérifié de bout en bout à fonctionner
   (`openai/gpt-oss-20b`, génération simple et JSON strict).
2. **OpenRouter** (nouveau, `infrastructure/llm/openrouter.py`) — agrège
   plusieurs modèles gratuits (suffixe `:free`) derrière une seule clé,
   même patron REST que Groq/Cerebras. Non vérifié de bout en bout faute de
   clé au moment de l'écriture.
3. **Cerebras** — clé valide mais compte nécessitant une facturation (HTTP
   402) ; reste dans la chaîne pour les comptes qui n'ont pas ce blocage.
4. **Gemini** — remis dans la chaîne (retiré par l'ADR 0006) : le projet
   Google testé était bloqué, mais rien n'indique qu'un autre projet le
   serait. Dernier maillon plutôt que retiré du code, pour ne pas perdre de
   couverture chez les lecteurs dont Gemini fonctionne.

## Conséquences

**Positives**
- Un run n'échoue plus à cause d'un seul fournisseur en panne/quota/bloqué :
  il faudrait que les 4 échouent simultanément.
- Aucun nouveau concept introduit : `OpenRouterLLM` suit exactement le patron
  `LLMPort` REST déjà établi (`GroqLLM`, `CerebrasLLM`, `GeminiLLM`) — pas de
  SDK, cohérent avec ADR 0003.
- `LLMSettings.has_any_provider` et `Container.llm` acceptent nativement 0 à
  4 clés configurées : configurer un seul fournisseur (ex. juste Groq) reste
  parfaitement valide, la chaîne se réduit d'elle-même.

**Négatives**
- 4 fournisseurs à surveiller/documenter au lieu de 2 : `.env.example`
  s'allonge en conséquence.
- Seuls Groq et Gemini (partiellement, hors blocage de projet) ont été
  vérifiés de bout en bout avec une vraie clé au moment de l'écriture ;
  OpenRouter reste à valider dès qu'une clé sera disponible.
- Le rate limiter local (`shared/rate_limiter.py`) suppose des quotas
  RPM/RPD stables ; les valeurs par défaut d'OpenRouter (`OPENROUTER_RPD=200`)
  sont une estimation prudente, pas un chiffre contractuel vérifié.

## Vérification

```bash
blogseo check
# doit lister les 4 fournisseurs dans l'ordre Groq → OpenRouter → Cerebras → Gemini
# avec le statut de clé (configurée/absente) de chacun

python -m pytest tests/unit/test_openrouter_llm.py tests/unit/test_cerebras_llm.py \
                 tests/unit/test_llm_fallback.py -v
```
