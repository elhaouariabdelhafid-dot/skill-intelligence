"""Sérialise les 3 agents ET ajoute une pause au nœud retrieve pour lisser
la consommation sous la limite 6000 tokens/min de Groq 8B."""
from pathlib import Path
import sys

p = Path("agents/graph.py")
if not p.exists():
    print("ERREUR: lancer depuis ~/skill-intelligence"); sys.exit(1)
s = p.read_text()

# 1) Sérialiser
old = '''    # retrieve -> les 3 agents en parallèle
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grader")
    g.add_edge("retrieve", "reasoner")
    g.add_edge("retrieve", "critic")
    # les 3 agents -> aggregator (LangGraph attend que les 3 finissent)
    g.add_edge("grader", "aggregator")
    g.add_edge("reasoner", "aggregator")
    g.add_edge("critic", "aggregator")
    g.add_edge("aggregator", END)'''
new = '''    # Agents SÉQUENTIELS pour respecter la limite 6000 tokens/min de Groq 8B.
    # Le parallèle envoyait les 3 prompts dans la même minute -> 429.
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grader")
    g.add_edge("grader", "reasoner")
    g.add_edge("reasoner", "critic")
    g.add_edge("critic", "aggregator")
    g.add_edge("aggregator", END)'''
if old in s:
    s = s.replace(old, new)

# 2) Réduire le contexte (5 chunks -> 3) pour alléger chaque prompt
s = s.replace("chunks = retrieve_final(state[\"question\"], top_k=5)",
              "chunks = retrieve_final(state[\"question\"], top_k=3)")

# 3) Ajouter une pause entre agents : on enveloppe grade/reason/criticize
#    via un petit wrapper dans graph.py au lieu de modifier chaque agent
if "import time" not in s:
    s = s.replace("from langgraph.graph import END, START, StateGraph",
                  "import time\nfrom langgraph.graph import END, START, StateGraph")

# wrapper: on redéfinit les noeuds pour insérer une pause avant chaque appel
old_nodes = '''    g.add_node("retrieve", retrieve_context_node)
    g.add_node("grader", grade)
    g.add_node("reasoner", reason)
    g.add_node("critic", criticize)
    g.add_node("aggregator", aggregate)'''
new_nodes = '''    def _paced(fn):
        def wrapped(state):
            time.sleep(4)  # respecte 6000 tokens/min de Groq 8B
            return fn(state)
        return wrapped

    g.add_node("retrieve", retrieve_context_node)
    g.add_node("grader", _paced(grade))
    g.add_node("reasoner", _paced(reason))
    g.add_node("critic", _paced(criticize))
    g.add_node("aggregator", aggregate)'''
if old_nodes in s:
    s = s.replace(old_nodes, new_nodes)

p.write_text(s)
print("graph.py : sérialisé + pauses + contexte réduit")
