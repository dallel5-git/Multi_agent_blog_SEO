"""Publication Git : `git add` + `commit` + `push` sur le dépôt du blog.

C'est le chemin ✅ « Publier » du bot Telegram : le push sur `main` déclenche
automatiquement le déploiement Vercel du blog.

Précautions volontaires :
- on ne commite QUE les fichiers produits par le pipeline (jamais `git add -A`),
  pour ne pas emporter le travail en cours de l'auteur ;
- si le push échoue (pas de credentials, réseau coupé), le commit reste local et
  le message d'erreur explique quoi faire — le fichier n'est jamais perdu.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ...domain.errors import PublicationError
from ...domain.ports.publishing import GitPublisherPort, PushResult

logger = logging.getLogger(__name__)


class GitPublisher(GitPublisherPort):
    """Wrapper minimal autour de la CLI `git`."""

    def __init__(
        self,
        repo_dir: Path,
        *,
        branch: str = "main",
        remote: str = "origin",
        user_name: str = "blogseo-bot",
        user_email: str = "bot@local",
        timeout_s: int = 120,
    ) -> None:
        self.repo_dir = repo_dir
        self.branch = branch
        self.remote = remote
        self.user_name = user_name
        self.user_email = user_email
        self.timeout_s = timeout_s

    # ------------------------------------------------------------------ #
    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        logger.debug("git %s", " ".join(args))
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except FileNotFoundError as exc:
            raise PublicationError("La commande `git` est introuvable sur ce système") from exc
        except subprocess.TimeoutExpired as exc:
            raise PublicationError(f"git {args[0]} a dépassé le délai de {self.timeout_s}s") from exc

        if check and result.returncode != 0:
            raise PublicationError(
                f"`git {' '.join(args)}` a échoué (code {result.returncode}) : "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        return result

    def _ensure_repo(self) -> None:
        if not (self.repo_dir / ".git").exists():
            raise PublicationError(f"{self.repo_dir} n'est pas un dépôt Git")

    def is_clean(self) -> bool:
        self._ensure_repo()
        result = self._run("status", "--porcelain", check=False)
        return not result.stdout.strip()

    # ------------------------------------------------------------------ #
    def commit_and_push(self, paths: list[Path], message: str) -> PushResult:
        self._ensure_repo()
        if not paths:
            raise PublicationError("Aucun fichier à commiter")

        # Identité locale au dépôt : on ne touche pas à la config globale de l'auteur.
        self._run("config", "user.name", self.user_name, check=False)
        self._run("config", "user.email", self.user_email, check=False)

        relative = []
        for path in paths:
            try:
                relative.append(str(path.resolve().relative_to(self.repo_dir.resolve())))
            except ValueError as exc:
                raise PublicationError(f"{path} est en dehors du dépôt {self.repo_dir}") from exc

        self._run("add", "--", *relative)

        staged = self._run("diff", "--cached", "--name-only", check=False).stdout.strip()
        if not staged:
            logger.info("Aucun changement à commiter (contenu identique)")
            return PushResult(committed=False, pushed=False, branch=self.branch,
                              message="contenu identique, rien à commiter")

        self._run("commit", "-m", message)
        sha = self._run("rev-parse", "--short", "HEAD").stdout.strip()
        logger.info("Commit créé : %s — %s", sha, message)

        push = self._run("push", self.remote, f"HEAD:{self.branch}", check=False)
        if push.returncode != 0:
            detail = (push.stderr or push.stdout).strip()
            logger.error("Push échoué : %s", detail)
            return PushResult(
                committed=True, pushed=False, commit_sha=sha, branch=self.branch,
                message=(
                    f"Commit {sha} créé localement mais push refusé : {detail[:300]}. "
                    f"Lancez `git push {self.remote} {self.branch}` manuellement."
                ),
            )

        logger.info("Push réussi sur %s/%s → déploiement Vercel déclenché", self.remote, self.branch)
        return PushResult(
            committed=True, pushed=True, commit_sha=sha, branch=self.branch,
            message=f"Commit {sha} poussé sur {self.remote}/{self.branch}",
        )
