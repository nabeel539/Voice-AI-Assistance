"""
CIMET Reconnect — LangGraph Recovery Agent Graph

Defines and compiles the explicit state graph controlling the recovery conversation workflow.
"""

from typing import Optional
from langgraph.graph import StateGraph, START, END

from app.agent.nodes import AgentNodeHandler, AgentWorkflowState
from app.agent.tools import AgentToolbox
from app.domain.call_state import CallState
from app.domain.models import ConsentStatus


def build_recovery_graph(toolbox: Optional[AgentToolbox] = None):
    """Build and compile the LangGraph StateGraph for energy journey recovery."""
    handler = AgentNodeHandler(toolbox=toolbox)

    graph = StateGraph(AgentWorkflowState)

    # 1. Register nodes
    graph.add_node("dnc_check", handler.dnc_check_node)
    graph.add_node("guardrails", handler.guardrail_node)
    graph.add_node("consent", handler.consent_node)
    graph.add_node("process_field", handler.process_field_node)
    graph.add_node("submit_journey", handler.submit_journey_node)

    # 2. Add edges and conditional routing
    graph.add_edge(START, "guardrails")

    def route_after_guardrails(state: AgentWorkflowState) -> str:
        """Route to handoff or end if guardrail triggered, otherwise check consent or process field."""
        if state.get("status") in ("handed_off", "declined"):
            return END
        if state.get("next_node") == "await_field_input":
            return END
        call_state = state["call_state"]
        if call_state.consent_status != ConsentStatus.CONSENTED:
            return "consent"
        return "process_field"


    graph.add_conditional_edges(
        "guardrails",
        route_after_guardrails,
        {
            "consent": "consent",
            "process_field": "process_field",
            END: END,
        }
    )

    def route_after_consent(state: AgentWorkflowState) -> str:
        """Route to END if declined, or wait for customer if active."""
        if state.get("status") == "declined":
            return END
        return END  # Pauses turn for customer response

    graph.add_conditional_edges(
        "consent",
        route_after_consent,
        {
            END: END,
        }
    )

    def route_after_field(state: AgentWorkflowState) -> str:
        """Route to submit if all done, END if handed off, or END to pause turn."""
        if state.get("status") in ("handed_off", "declined"):
            return END
        return END

    graph.add_conditional_edges(
        "process_field",
        route_after_field,
        {
            END: END,
        }
    )

    return graph.compile()


class EnergyRecoveryAgent:
    """High-level runner interface wrapping the compiled LangGraph workflow."""

    def __init__(self, toolbox: Optional[AgentToolbox] = None):
        self.toolbox = toolbox or AgentToolbox()
        self.handler = AgentNodeHandler(self.toolbox)
        self.compiled_graph = build_recovery_graph(self.toolbox)

    def start_call(self, call_state: CallState) -> AgentWorkflowState:
        """Initiate the call by running DNC check and generating the consent prompt."""
        initial_state: AgentWorkflowState = {
            "call_state": call_state,
            "customer_utterance": "",
            "confidence": 1.0,
            "agent_message": "",
            "status": "pending",
        }
        return self.handler.dnc_check_node(initial_state)

    def process_turn(
        self,
        call_state: CallState,
        customer_utterance: str,
        confidence: float = 1.0,
    ) -> AgentWorkflowState:
        """Process a customer conversational turn through the compiled LangGraph workflow."""
        input_state: AgentWorkflowState = {
            "call_state": call_state,
            "customer_utterance": customer_utterance,
            "confidence": confidence,
            "agent_message": "",
            "status": "active",
        }
        result = self.compiled_graph.invoke(input_state)
        return result

