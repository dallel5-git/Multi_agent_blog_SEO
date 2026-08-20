#!/usr/bin/env bash
# =============================================================================
#  Crée le backlog complet sur GitHub : labels, milestones et issues.
#
#  Prérequis :
#    1. La CLI GitHub :  https://cli.github.com/
#    2. Être authentifié :  gh auth login
#
#  Usage :
#    ./scripts/create_github_issues.sh                 # sur le dépôt par défaut
#    ./scripts/create_github_issues.sh --dry-run       # affiche sans rien créer
#    REPO=moncompte/monrepo ./scripts/create_github_issues.sh
#
#  Le script est IDEMPOTENT : relancé, il ne crée pas de doublon (il compare
#  les titres d'issues existants).
# =============================================================================

set -euo pipefail

REPO="${REPO:-dallel5-git/Multi_agent_blog_SEO}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/github"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 1 ;;
  esac
done

# --- Vérifications ----------------------------------------------------------
command -v gh >/dev/null 2>&1 || {
  echo "❌ La CLI GitHub (gh) n'est pas installée."
  echo "   Installation : https://cli.github.com/"
  echo "   Debian/Ubuntu : sudo apt install gh"
  exit 1
}
command -v python3 >/dev/null 2>&1 || { echo "❌ python3 est requis."; exit 1; }

if ! gh auth status >/dev/null 2>&1; then
  echo "❌ Vous n'êtes pas authentifié. Lancez d'abord :  gh auth login"
  exit 1
fi

for f in labels.json milestones.json issues.json; do
  [[ -f "$DATA_DIR/$f" ]] || { echo "❌ Fichier manquant : $DATA_DIR/$f"; exit 1; }
done

echo "╭──────────────────────────────────────────────────────────────╮"
echo "│  Création du backlog sur $REPO"
$DRY_RUN && echo "│  MODE SIMULATION — rien ne sera créé"
echo "╰──────────────────────────────────────────────────────────────╯"
echo

# --- 1. Labels --------------------------------------------------------------
echo "▶ Labels"
python3 -c "
import json,sys
for l in json.load(open('$DATA_DIR/labels.json',encoding='utf-8')):
    print('\t'.join([l['name'], l['color'], l['description']]))
" | while IFS=$'\t' read -r name color description; do
  if $DRY_RUN; then
    echo "  · [simulation] label « $name »"
  elif gh label create "$name" --repo "$REPO" --color "$color" --description "$description" >/dev/null 2>&1; then
    echo "  ✔ créé   : $name"
  else
    gh label edit "$name" --repo "$REPO" --color "$color" --description "$description" >/dev/null 2>&1 \
      && echo "  ↻ à jour : $name" \
      || echo "  ⚠ ignoré : $name"
  fi
done
echo

# --- 2. Milestones ----------------------------------------------------------
echo "▶ Milestones"
existing_ms="$($DRY_RUN && echo "" || gh api "repos/$REPO/milestones?state=all" --jq '.[].title' 2>/dev/null || echo "")"
python3 -c "
import json
for m in json.load(open('$DATA_DIR/milestones.json',encoding='utf-8')):
    print('\t'.join([m['title'], m['description']]))
" | while IFS=$'\t' read -r title description; do
  if $DRY_RUN; then
    echo "  · [simulation] milestone « $title »"
  elif grep -Fxq "$title" <<< "$existing_ms"; then
    echo "  ↻ existe : $title"
  else
    gh api "repos/$REPO/milestones" -f title="$title" -f description="$description" >/dev/null 2>&1 \
      && echo "  ✔ créé   : $title" \
      || echo "  ⚠ échec  : $title"
  fi
done
echo

# --- 3. Issues --------------------------------------------------------------
echo "▶ Issues"
if $DRY_RUN; then
  EXISTING=""
else
  EXISTING="$(gh issue list --repo "$REPO" --state all --limit 500 --json title --jq '.[].title' 2>/dev/null || echo "")"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$DATA_DIR/issues.json" "$TMP" <<'PYEOF'
import json, sys, pathlib
data = json.load(open(sys.argv[1], encoding="utf-8"))
tmp = pathlib.Path(sys.argv[2])
index = []
for i, issue in enumerate(data):
    body_file = tmp / f"body_{i}.md"
    body_file.write_text(issue["body"], encoding="utf-8")
    index.append("\t".join([
        issue["title"],
        ",".join(issue["labels"]),
        issue["milestone"],
        str(body_file),
        "close" if issue.get("close") else "open",
    ]))
(tmp / "index.tsv").write_text("\n".join(index), encoding="utf-8")
PYEOF

created=0; skipped=0; closed=0
while IFS=$'\t' read -r title labels milestone body_file state; do
  [[ -z "$title" ]] && continue

  if grep -Fxq "$title" <<< "$EXISTING"; then
    echo "  ↻ existe : $title"
    skipped=$((skipped+1))
    continue
  fi

  if $DRY_RUN; then
    echo "  · [simulation] $title  [$labels]  ($milestone)"
    created=$((created+1))
    continue
  fi

  url="$(gh issue create --repo "$REPO" \
        --title "$title" \
        --body-file "$body_file" \
        --label "$labels" \
        --milestone "$milestone" 2>/dev/null)" || {
    # Repli sans milestone si celui-ci n'existe pas encore côté API.
    url="$(gh issue create --repo "$REPO" --title "$title" --body-file "$body_file" --label "$labels")"
  }
  echo "  ✔ créée  : $title"
  created=$((created+1))

  # Les issues du périmètre déjà livré sont refermées aussitôt : l'historique
  # du dépôt reflète ainsi le travail réel et sert de documentation.
  if [[ "$state" == "close" ]]; then
    gh issue close "$url" --repo "$REPO" --reason completed --comment "Livré en v1.0.0." >/dev/null 2>&1 \
      && closed=$((closed+1))
  fi
  sleep 0.7   # courtoisie envers l'API GitHub
done < "$TMP/index.tsv"

echo
echo "╭──────────────────────────────────────────────────────────────╮"
echo "│  Terminé : $created créée(s), $skipped déjà présente(s), $closed fermée(s)"
echo "│  → https://github.com/$REPO/issues"
echo "╰──────────────────────────────────────────────────────────────╯"
