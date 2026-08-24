"""Contrat commun des pipelines de plateforme.

TODO — Lot 3 : définir `PlatformPipeline`, classe de base abstraite reprenant
la philosophie de `blogseo.application.agents.base.Agent` :

    class PlatformPipeline(ABC):
        platform: Platform
        def watch(self) -> list[TrendItem]: ...      # veille propre à la plateforme
        def choose_topic(self, trends) -> Topic: ... # sujet propre à la plateforme
        def write(self, topic) -> Draft: ...         # rédaction, Brand Kernel chargé ici
        def submit(self, draft) -> None: ...         # envoi au bot Telegram dédié

Deux règles héritées de l'existant :

1. un pipeline n'en connaît jamais un autre ;
2. une source de veille morte dégrade le run, elle ne le fait jamais échouer.

La consultation du calendrier partagé pour une mention croisée se fait dans
`write()`, et reste facultative.
"""
