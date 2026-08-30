#!/usr/bin/env bash
# =============================================================================
#  Installe le pipeline comme service utilisateur systemd, déclenché toutes les
#  48 h. Aucun droit root nécessaire.
#
#  Usage :  ./scripts/install_systemd_timer.sh
#  Désinstaller :  ./scripts/install_systemd_timer.sh --uninstall
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="blogseo.service"
TIMER="blogseo.timer"

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl --user disable --now "$TIMER" 2>/dev/null || true
  rm -f "$UNIT_DIR/$SERVICE" "$UNIT_DIR/$TIMER"
  systemctl --user daemon-reload
  echo "✔ Service et timer désinstallés."
  exit 0
fi

command -v systemctl >/dev/null 2>&1 || { echo "❌ systemd introuvable sur ce système."; exit 1; }

# Interpréteur : le venv du projet s'il existe, sinon python3 du système.
PYTHON="$PROJECT_DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
echo "▶ Interpréteur : $PYTHON"

[[ -f "$PROJECT_DIR/.env" ]] || {
  echo "⚠️  Aucun fichier .env trouvé dans $PROJECT_DIR"
  echo "    Copiez .env.example en .env et renseignez vos clés avant de continuer."
}

mkdir -p "$UNIT_DIR"

cat > "$UNIT_DIR/$SERVICE" <<UNIT
[Unit]
Description=blogseo — génération d'un article de blog SEO
Documentation=file://${PROJECT_DIR// /%%20}/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart="$PYTHON" -c "from blogseo.interfaces.scheduler import run_once; run_once()"
# Le pipeline attend la validation Telegram : jusqu'à 24 h + marge.
TimeoutStartSec=90000
StandardOutput=journal
StandardError=journal
Environment="PYTHONPATH=$PROJECT_DIR/src"
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
UNIT

cat > "$UNIT_DIR/$TIMER" <<UNIT
[Unit]
Description=Déclenche blogseo toutes les 48 heures
Documentation=file://${PROJECT_DIR// /%%20}/README.md

[Timer]
# Premier déclenchement 10 minutes après le démarrage de la session,
# puis toutes les 48 heures.
OnBootSec=10min
OnUnitActiveSec=48h
# Rattrape un déclenchement manqué si la machine était éteinte.
Persistent=true
# Décalage aléatoire pour ne pas taper les API à la seconde près.
RandomizedDelaySec=30min
Unit=$SERVICE

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$TIMER"

# Permet au timer de tourner même hors session graphique.
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$USER" 2>/dev/null \
    && echo "✔ Linger activé : le timer tournera même sans session ouverte." \
    || echo "⚠️  Impossible d'activer le linger (droits ?). Le timer ne tournera que session ouverte."
fi

echo
echo "✔ Installation terminée."
echo
systemctl --user list-timers "$TIMER" --no-pager || true
echo
echo "Commandes utiles :"
echo "  systemctl --user list-timers blogseo.timer   # prochaine exécution"
echo "  systemctl --user start blogseo.service       # déclencher maintenant"
echo "  journalctl --user -u blogseo.service -f      # logs en direct"
echo "  systemctl --user stop blogseo.timer          # mettre en pause"
echo "  ./scripts/install_systemd_timer.sh --uninstall"
