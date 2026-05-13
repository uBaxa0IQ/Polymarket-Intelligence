"""Build and compile the LangGraph pipeline."""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graph.state import PipelineState
from app.graph import nodes


def build_graph():
    """Build and compile the full pipeline graph."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("screen_markets", nodes.screen_markets)
    graph.add_node("rank_markets", nodes.rank_markets)
    graph.add_node("select_top_n", nodes.select_top_n)
    graph.add_node("analyze_market", nodes.analyze_market)
    graph.add_node("decide_all", nodes.decide_all)
    graph.add_node("execute_bets", nodes.execute_bets)

    # Edges
    graph.set_entry_point("screen_markets")
    graph.add_edge("screen_markets", "rank_markets")
    graph.add_edge("rank_markets", "select_top_n")

    # Fan-out: select_top_n → analyze_market (one per market, parallel via Send)
    graph.add_conditional_edges(
        "select_top_n",
        nodes.fan_out_to_markets,
        ["analyze_market"],
    )

    # Fan-in: after all analyze_market complete → decide_all
    graph.add_edge("analyze_market", "decide_all")
    graph.add_edge("decide_all", "execute_bets")
    graph.add_edge("execute_bets", END)

    return graph.compile()


# Lazy singleton — compiled on first use, not at import time
_pipeline_graph = None


def get_pipeline_graph():
    global _pipeline_graph
    if _pipeline_graph is None:
        _pipeline_graph = build_graph()
    return _pipeline_graph
