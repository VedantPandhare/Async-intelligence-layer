from langgraph.graph import END, StateGraph

from .blocker_inference import blocker_inference_node
from .dep_conflict import dep_conflict_node
from .digest_assembler import digest_assembler_node
from .intervention import intervention_node
from .narrative_writer import narrative_writer_node
from .signal_collector import signal_collector_node
from .state import AgentState


def _should_intervene(state: AgentState) -> str:
    """Conditional edge: only run intervention if critical blockers exist."""
    if state.get("should_intervene"):
        return "intervention"
    return "end"


def build_pipeline() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("signal_collector", signal_collector_node)
    graph.add_node("blocker_inference", blocker_inference_node)
    graph.add_node("dep_conflict", dep_conflict_node)
    graph.add_node("narrative_writer", narrative_writer_node)
    graph.add_node("digest_assembler", digest_assembler_node)
    graph.add_node("intervention", intervention_node)

    graph.set_entry_point("signal_collector")
    graph.add_edge("signal_collector", "blocker_inference")
    graph.add_edge("blocker_inference", "dep_conflict")
    graph.add_edge("dep_conflict", "narrative_writer")
    graph.add_edge("narrative_writer", "digest_assembler")

    graph.add_conditional_edges(
        "digest_assembler",
        _should_intervene,
        {"intervention": "intervention", "end": END},
    )
    graph.add_edge("intervention", END)

    return graph.compile()


pipeline = build_pipeline()
