# Mise en place Meta Graph API (Facebook + Instagram)

> Procédure administrative pour `stats_collector/meta_graph.py` (Lot 5,
> issue « Implémenter le collecteur Meta »). Rien de tout ceci ne se fait en
> code — c'est la partie manuelle que CADRAGE.md (risque n°3) demande de
> démarrer tôt, en parallèle des premiers lots.

## 1. Compte Meta Business

1. Aller sur [business.facebook.com](https://business.facebook.com/) et créer
   un compte Meta Business s'il n'en existe pas déjà un.
2. Rattacher (ou créer) la Page Facebook du projet à ce compte Business.

## 2. Page Facebook

La Page Facebook existante (`facebook.com/profile.php?id=...`, voir
`brand_kernel.yaml` → `identity.handles.facebook`) doit être gérée par ce
compte Business. Noter son **Page ID** (visible dans Paramètres de la Page →
À propos, ou via l'API une fois le jeton obtenu).

## 3. Compte Instagram Business relié

1. Convertir le compte Instagram en compte **Professionnel → Entreprise**
   (Paramètres Instagram → Compte → Passer à un compte professionnel).
2. Relier ce compte Instagram à la Page Facebook (Paramètres de la Page →
   Comptes liés → Instagram).
3. Récupérer l'**Instagram Business Account ID** via le Graph API Explorer
   (`GET /{page-id}?fields=instagram_business_account`), une fois l'étape 4
   faite.

## 4. Application Meta

1. Sur [developers.facebook.com](https://developers.facebook.com/), créer une
   application (type « Entreprise » suffit).
2. Ajouter le produit **Facebook Login** et/ou utiliser directement le
   [Graph API Explorer](https://developers.facebook.com/tools/explorer/) —
   le mode développement suffit tant que seuls les comptes du développeur
   (les vôtres) sont concernés : pas besoin de review Meta pour ce projet.

## 5. Jeton de page longue durée

1. Dans le Graph API Explorer, sélectionner l'application créée, puis la
   Page, et générer un **jeton d'accès utilisateur** avec les permissions
   `pages_read_engagement`, `pages_show_list`, `instagram_basic`,
   `instagram_manage_insights`.
2. Échanger ce jeton court terme contre un **jeton de page longue durée**
   (~60 jours) :

   ```
   GET https://graph.facebook.com/v19.0/oauth/access_token
       ?grant_type=fb_exchange_token
       &client_id=<APP_ID>
       &client_secret=<APP_SECRET>
       &fb_exchange_token=<JETON_COURT_TERME>
   ```

3. Renseigner le résultat dans `.env` :

   ```
   META_PAGE_ACCESS_TOKEN=...
   META_PAGE_ID=...
   META_INSTAGRAM_BUSINESS_ID=...
   ```

## Expiration — ~60 jours

Le jeton expire. `stats_collector.meta_graph.token_days_remaining()` et
`token_renewal_reminder()` vérifient l'échéance (endpoint `/debug_token`) et
produisent un message actionnable quand il reste moins de
`TOKEN_RENEWAL_WARNING_DAYS` (7) jours — journalisé, et envoyable via
`pilotage check-meta-token` (voir `cli.py`). Un jeton expiré ne fait jamais
planter le collecteur : `FacebookStatsCollector`/`InstagramStatsCollector`
détectent l'erreur Meta `code 190` (OAuthException) et journalisent un
message clair plutôt qu'une trace d'exception brute.

Pour renouveler : reprendre l'étape 5 avec un nouveau jeton court terme.
