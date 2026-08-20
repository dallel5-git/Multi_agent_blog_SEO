# ADR 0003 — Stack 100 % gratuite, sans exception

- **Statut :** accepté
- **Date :** 2026-08-19

## Contexte

Contrainte explicite du propriétaire : **le système doit tourner sans jamais
sortir une carte bancaire.** Ce n'est pas une préférence de coût, c'est une
contrainte d'accessibilité — le projet sert aussi de démonstration pour un
public tunisien où le paiement en ligne international est difficile.

## Décision

| Besoin | Retenu | Écarté |
|---|---|---|
| LLM principal | Google Gemini free tier | OpenAI, Anthropic (payants) |
| LLM secours | Groq free tier | — |
| Recherche | `ddgs` (DuckDuckGo), Tavily free tier en option | SerpAPI (payant) |
| Tendances | `pytrends` | Semrush, Ahrefs (payants) |
| Embeddings | `sentence-transformers` local CPU | OpenAI embeddings (payant) |
| Vector store | ChromaDB local | Pinecone, Weaviate Cloud (payants) |
| Images | Pollinations.ai + repli Pillow | DALL·E, Midjourney (payants) |
| Notifications | Telegram Bot API | Twilio, SendGrid (payants) |

**Interdiction absolue :** aucun SDK ni appel vers un service payant, même en
option, même commenté « à activer plus tard ».

Mesures d'accompagnement :

- rate limiter à double fenêtre (minute + jour), persisté sur disque, qui bloque
  **avant** l'appel plutôt que d'encaisser un 429 ;
- bascule automatique Gemini → Groq sur quota ;
- toutes les dépendances lourdes sont optionnelles avec un repli fonctionnel.

## Conséquences

**Positives**
- Coût réel : 0 €. Reproductible par n'importe quel lecteur du blog.
- Aucune dépendance à un compte de facturation qui pourrait être suspendu.
- ~7 à 9 appels LLM par run, soit environ 0,6 % du quota Gemini gratuit.

**Négatives**
- Qualité de rédaction en retrait par rapport aux modèles premium.
- Quotas à surveiller ; d'où le rate limiter et la chaîne de fallback.
- Pollinations et pytrends n'ont aucune garantie de service ; traités comme
  optionnels, avec repli.

## Vérification

```bash
grep -rniE "openai|anthropic|pinecone|serpapi" src/ requirements.txt
# ne doit renvoyer que des mentions dans les commentaires d'interdiction
```
