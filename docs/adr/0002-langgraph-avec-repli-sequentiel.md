# ADR 0002 — LangGraph, avec un exécuteur séquentiel de secours

- **Statut :** accepté
- **Date :** 2026-08-19

## Contexte

Le pipeline n'est pas linéaire : le Quality Gate peut renvoyer l'article au
Content Writer, et le bouton 🔁 de Telegram aussi. Coder ces boucles en `while`
imbriqués rend le flux difficile à lire et à modifier.

Par ailleurs, LangGraph tire une dépendance non négligeable, et le projet doit
rester installable et fonctionnel même dans un environnement minimal.

## Décision

1. Décrire la topologie **une seule fois**, de façon déclarative, dans
   `orchestrator/pipeline_spec.py` : `LINEAR_EDGES`, `ROUTES`, `ENTRY_POINT`.
2. Fournir **deux exécuteurs** qui consomment cette même description :
   - `graph.LangGraphOrchestrator` — nominal ;
   - `sequential.SequentialOrchestrator` — sans dépendance externe.
3. `build_orchestrator()` choisit selon `ORCHESTRATOR` et retombe
   automatiquement sur le séquentiel si LangGraph est absent ou si la
   compilation du graphe échoue.

## Conséquences

**Positives**
- Les deux boucles de feedback sont déclarées, pas codées en dur.
- `blogseo graph` produit un diagramme Mermaid à jour, utilisable en documentation.
- Le pipeline tourne à l'identique sans LangGraph ; les tests de routage
  s'exécutent sur les fonctions de routage pures.

**Négatives**
- Deux exécuteurs à maintenir. Mitigé par le fait qu'ils partagent la même
  description de topologie et que les fonctions de routage sont testées à part.

## Note d'implémentation importante

`StateGraph(dict)` fait passer tout l'état par un canal racine `__root__` en
`LastValue`, qui refuse deux écritures dans un même pas et fait échouer
`draw_mermaid()`. Il faut un **`TypedDict`** avec une clé nommée :

```python
class GraphState(TypedDict):
    state: PipelineState
builder = StateGraph(GraphState)
```
