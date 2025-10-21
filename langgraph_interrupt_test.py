from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import JsonPlusSerializer, BaseCheckpointSaver
from langgraph.types import interrupt, Interrupt
import sqlite3
import tempfile
from pydantic import BaseModel, Field
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables import RunnableConfig

import typing as t
import sys
import pprint

from deepmerge import always_merger


class SomeStuff(BaseModel):
    query: str
    approved: bool = False


# Define your graph state
class GraphState(BaseModel):
    query: str = ""
    approved: bool = False

def do_something(dont_care_state) -> GraphState:
    print(f"1️⃣ Doing something first: {dont_care_state}")
    return GraphState(query='This is a sensitive_action', approved=False)

# Define a node that might dynamically interrupt
def check_for_approval(state: GraphState) -> GraphState:
    print(f"Checking for approval: {state}")
    if "sensitive_action" in state.query and not state.approved:
        # Dynamically interrupt if a sensitive action is detected and not approved
        print("⚠️ Sensitive action detected, interrupting for approval...")
        interrupt("User intervention required")
        print("After interrupt")
    return state

def run_workflow(sqlite_path: str = None):
    # Build the graph
    workflow = StateGraph(GraphState)
    workflow.add_node("do_something", do_something)
    workflow.add_node("check_approval", check_for_approval)
    workflow.add_edge("do_something", "check_approval")
    workflow.set_entry_point("do_something")
    workflow.add_edge("check_approval", END) # Or to another node after approval

    # Create temporary SQLite database
    db_path = sqlite_path or tempfile.mktemp(suffix=".db")
    print(f"📁 Using SQLite database: {db_path}")

    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Compile the graph with a checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "dynamic_interrupt_demo"}}

    current_state = app.get_state(config)
    has_checkpoint = current_state.values is not None and len(current_state.values) > 0

    keep_going = True
    while keep_going:
        # result = app.invoke(state, config=config)
        result = app.invoke(None if has_checkpoint else GraphState(), config=config)
        match (result, GraphState.model_validate(result)):
            case (_, GraphState(approved=True)):
                print("✅ Workflow successful.\nFinal state:", result)
                # Continue to next node or finish
                keep_going = False
            case ({'__interrupt__': [Interrupt(value=msg)]}, state):
                print(f"⚠️ Workflow interrupted: {msg}")
                response = input("Approve action? (y/n): ").strip().lower()
                if response == 'y':
                    state.approved = True
                app.update_state(config, state)
                has_checkpoint = True

                # Test...returning to make sure result works
                return
            case _:
                print("✅ No approval, trying again:", result)
                has_checkpoint = True

def test_serializer():
    serde = JsonPlusSerializer()

    ser_bytes = serde.dumps(GraphState(query="test", approved=False))
    print('TypeDict ser: ' + ser_bytes.decode('utf-8'))

    type_name, ser_bytes = serde.dumps_typed(GraphState(query="test", approved=False))
    print(type_name)
    print('Typed dict ser + type' + str(ser_bytes))

    ser_bytes = serde.dumps(SomeStuff(query="test", approved=False))
    print('Pydantic ser: ' + ser_bytes.decode('utf-8'))

    pydantic_deser = serde.loads(ser_bytes)
    print(f'Pydantic deserialized: {pydantic_deser}')
    pass

class OuterGraphState(BaseModel):
    prompt: str
    approved: bool = False
    times_that_something_was_done: int = 0
    times_that_approval_was_verified: int = 0
    
class SubgraphState(BaseModel):
    outer_graph_state: OuterGraphState
    times_pre_step_was_run: int = 0
    times_post_step_was_run: int = 0

def setup_workflow_with_subgraph() -> CompiledStateGraph:
    def do_something(state: OuterGraphState) -> OuterGraphState:
        state.times_that_something_was_done += 1
        return state

    def subgraph_pre_step(state: OuterGraphState) -> SubgraphState:
        return SubgraphState(outer_graph_state=state, times_pre_step_was_run=1)

    def subgraph_check_for_approval(state: SubgraphState) -> SubgraphState:
        state.outer_graph_state.times_that_approval_was_verified += 1
        if state.outer_graph_state.approved:
            print("✅ Action approved, continuing...")
            return state

        if "sensitive_action" in state.outer_graph_state.prompt and not state.outer_graph_state.approved:
            print("⚠️ Sensitive action detected, interrupting for approval...")
            interrupt("User intervention required")
        return state

    def subgraph_post_step(state: SubgraphState) -> OuterGraphState:
        state.times_post_step_was_run += 1
        return state.outer_graph_state

    workflow = StateGraph(SubgraphState)
    workflow.add_node("do_something", do_something)

    subgraph = StateGraph(OuterGraphState, context_schema=None, input_schema=OuterGraphState, output_schema=OuterGraphState)
    subgraph.add_sequence([
        ("pre_step", subgraph_pre_step),
        ("check_approval", subgraph_check_for_approval),
        ("post_step", subgraph_post_step),
    ])
    subgraph.set_entry_point("pre_step")
    subgraph.add_edge("post_step", END)
    
    workflow.add_node("subgraph", subgraph.compile(checkpointer=True))
    workflow.add_edge("do_something", "subgraph")
    workflow.set_entry_point("do_something")
    workflow.add_edge("subgraph", END)
    
    # Create temporary SQLite database
    # db_path = tempfile.mktemp(suffix=".db")
    # print(f"📁 Using SQLite database: {db_path}")

    # conn = sqlite3.connect(db_path, check_same_thread=False)
    # checkpointer = SqliteSaver(conn)
    
    checkpointer=InMemorySaver()

    return workflow.compile(checkpointer=checkpointer)

def test_langgraph_with_interrupt_in_subgraph():
    app = setup_workflow_with_subgraph()
    initial_state = OuterGraphState(prompt="Please perform a sensitive_action now.")
    configuration: RunnableConfig = {"configurable": {"thread_id": "test_thread_2"}}
    result = app.invoke(input=initial_state, config=configuration)
    result_state = OuterGraphState.model_validate(result)

    # This special __interrupt__ key is present if the graph was interrupted
    match result:
        case {"__interrupt__": [Interrupt() as interrupt]}:
            assert interrupt.value == "User intervention required"
        case _:
            assert False, "Expected an interrupt but did not get one."

    # Ensure that the state was updated correctly
    print(result_state.times_that_something_was_done)
    # Approval check will still be zero. When a LangGraph node interrupts,
    # the returned state is the state before the node was executed.
    print(result_state.times_that_approval_was_verified)
    
    # Ensure we can get the subgraph state as well
    # subgraph_state_raw = app.get_state(config=configuration, subgraphs=True)
    # subgraph_state = SubgraphState.model_validate(subgraph_state_raw.values)
    
    # Run a second time through the graph without approving.
    # input=None is crucial to get LangGraph to resume from the last persisted state.
    result = app.invoke(input=None, config=configuration)
    
    # This special __interrupt__ key is present if the graph was interrupted
    match result:
        case {"__interrupt__": [Interrupt() as interrupt]}:
            assert interrupt.value == "User intervention required"
        case _:
            assert False, "Expected an interrupt but did not get one."
    
    
    # result_state = OuterGraphState.model_validate(result)
    
    # Ensure we can get the subgraph state as well
    state_raw = app.get_state(config=configuration, subgraphs=True)
    interrupted_task = next(filter(lambda t: t.interrupts, state_raw.tasks), None)
    
    if interrupted_task:
        subgraph_state_raw = interrupted_task.state
        subgraph_state = SubgraphState.model_validate(subgraph_state_raw.values)
        subgraph_state.outer_graph_state.approved = True  # Simulate approval
        subgraph_config = always_merger.merge(configuration, {
            'configurable': {
                'checkpoint_ns': interrupted_task.name
            }
        })
        app.update_state(config=subgraph_config, values=subgraph_state)
    else:
        assert False, "Expected to find an interrupted task but did not."

    # ...and run another time.
    result = app.invoke(input=None, config=configuration)
    result_state = OuterGraphState.model_validate(result)
    print(result_state)
    
    assert result.get('__interrupt__', None) is None, "Did not expect an interrupt this time."


if __name__ == "__main__":
    # run_workflow(sys.argv[1] if len(sys.argv) > 1 else None)
    # test_serializer()
    test_langgraph_with_interrupt_in_subgraph()
