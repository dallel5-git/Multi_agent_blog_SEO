# Fiche de bord — Blog IA (pipeline & pilotage)

> Dernier balayage : 30 août 2026

Génération automatique d'articles de blog et de scripts multi-plateformes,
avec validation humaine sur Telegram avant toute publication.

## État actuel

| Élément | Statut |
|---|---|
| Blog | ✅ Automatique — un brouillon toutes les 48h |
| Bots de pilotage | ✅ 6 / 6 configurés |
| Stats YouTube | ✅ Clé validée |
| Stats Meta (Facebook/Instagram) | ⚠️ Jeton validé, Instagram Business ID manquant |
| Tests | ✅ Suite complète verte |

## 1. Le blog

Tourne seul depuis l'installation du timer systemd : un brouillon toutes les
48h, envoyé sur votre bot Telegram de validation. **Rien n'est publié sans
votre clic.**

### Le cycle de décision Telegram

Vous recevez le titre, un extrait, le score qualité et trois boutons :

| Bouton | Effet |
|---|---|
| ✅ Publier | Écrit dans le blog, commit + push Git, Vercel déploie en une minute. |
| ❌ Garder en local | Écrit dans le blog mais aucun push ; vous relisez et poussez vous-même. |
| 🔁 Faire réécrire | Retour au rédacteur avec vos remarques. |

### Commandes utiles

```bash
make check        # vérifie la configuration
make dry-run      # un run réel, rien n'est publié
make run          # un run réel, publication soumise à Telegram

systemctl --user list-timers blogseo.timer   # prochain déclenchement automatique
systemctl --user start blogseo.service       # déclencher maintenant
journalctl --user -u blogseo.service -f      # suivre un run en direct
```

## 2. Le pilotage multi-plateformes

Un bot Telegram privé par plateforme. La génération se fait à la demande,
une commande à la fois — **aucun processus qui tourne en continu**.

| Plateforme | Statut |
|---|---|
| YouTube | ✅ bot + stats prêts |
| TikTok | ✅ bot prêt |
| Instagram | ⚠️ ID Business manquant |
| X | ✅ bot prêt |
| Facebook | ✅ bot + stats prêts |
| Canal Telegram | ⚠️ bot pas encore admin du canal |

### Générer un contenu, obtenir le résultat, rien de plus

```bash
pilotage run youtube        # ou tiktok / instagram / x / facebook / telegram_channel
```

Génère le script, l'envoie sur le bot Telegram de la plateforme avec les
boutons ✅ ✏️ ❌, puis le processus s'arrête.

### Stats & tableau de bord

```bash
pilotage collect-stats youtube    # ou facebook / instagram / telegram_channel
pilotage check-meta-token         # jours restants avant expiration (~60j)
make dashboard-pilotage           # Kanban, stats, conversions — localhost:8501
```

## 3. Référence rapide

| Je veux… | Commande |
|---|---|
| Vérifier que tout est bien configuré | `make check` · `pilotage check` |
| Générer un article de blog maintenant | `systemctl --user start blogseo.service` |
| Générer un script pour une plateforme | `pilotage run <plateforme>` |
| Voir le tableau de bord | `make dashboard-pilotage` |
| Suivre un run en direct | `journalctl --user -u blogseo.service -f` |
| Mettre le blog en pause | `systemctl --user stop blogseo.timer` |

## 4. En attente de votre côté

- **Instagram Business ID** — une fois récupéré, ajoutez-le à
  `META_INSTAGRAM_BUSINESS_ID` dans `.env` pour activer la collecte de stats
  Instagram.
- **Bot du canal Telegram public** — à rendre administrateur du canal quand
  vous serez prêt à activer ses statistiques (nombre de membres).
- **Deux issues GitHub à clôturer manuellement** — #63 et #71 : toutes leurs
  sous-tâches sont fermées et le code est testé, mais fermer l'issue
  elle-même vous revient (action bloquée pour l'outil).
- **Fichiers modifiés non liés à cette session** — `.gitignore`,
  `ARCHITECTURE.md`, `CADRAGE.md`, `README.md`, `docs/BACKLOG.md`,
  `trend_sources.py` — laissés tels quels, à committer ou non selon votre
  jugement.

## Dépôts

- [Multi_agent_blog_SEO](https://github.com/dallel5-git/Multi_agent_blog_SEO) — le pipeline
- [oussama-ai-blog](https://github.com/dallel5-git/oussama-ai-blog) — le site
