"""Contrat commun des collecteurs.

TODO — Lot 5 : définir `StatsCollector` (port) avec

    def collect(self, since: date) -> list[StatSnapshot]: ...

Chaque adapter l'implémente. Un collecteur en panne journalise et rend une
liste vide : une API Meta indisponible ne doit jamais faire échouer la collecte
des autres plateformes.
"""
