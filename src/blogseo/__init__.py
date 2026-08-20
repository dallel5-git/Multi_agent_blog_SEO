"""blogseo — système multi-agents de génération d'articles SEO.

Architecture en couches (Clean Architecture) :

    interfaces/      CLI, scheduler, bot Telegram
        ↓
    orchestrator/    graphe LangGraph des 9 agents
        ↓
    application/     agents, cas d'usage, prompts        ← dépend des ports
        ↓
    domain/          entités, value objects, PORTS       ← ne dépend de RIEN
        ↑
    infrastructure/  adapters concrets (Gemini, Groq, DuckDuckGo, Chroma…)

La règle de dépendance ne pointe que vers l'intérieur : `domain` n'importe
jamais `infrastructure`. Le câblage se fait dans
`infrastructure/config/container.py`.
"""

__version__ = "1.0.0"
__author__ = "Oussama Dallel"
