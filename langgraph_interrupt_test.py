from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.base import JsonPlusSerializer, BaseCheckpointSaver
from langgraph.types import interrupt, Interrupt
import sqlite3
import tempfile
from pydantic import BaseModel, Field

import typing as t
import sys
import pprint


class SomeStuff(BaseModel):
    query: str
    approved: bool = False


# Define your graph state
class GraphState(t.TypedDict):
    query: str
    approved: bool

def do_something(dont_care_state) -> GraphState:
    print(f"1️⃣ Doing something first: {dont_care_state}")
    return GraphState(query='This is a sensitive_action', approved=False)

# Define a node that might dynamically interrupt
def check_for_approval(state: GraphState) -> GraphState:
    print(f"Checking for approval: {state}")
    if "sensitive_action" in state["query"] and not state["approved"]:
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

    pprint.pprint(current_state)

    keep_going = True
    while keep_going:
        # result = app.invoke(state, config=config)
        result = app.invoke(None if has_checkpoint else {}, config=config)
        match result:
            case {'approved': True}:
                print("✅ Workflow successful.\nFinal state:", result)
                # Continue to next node or finish
                keep_going = False
            case {'__interrupt__': [Interrupt(value=msg)]}:
                print(f"⚠️ Workflow interrupted: {msg}")
                response = input("Approve action? (y/n): ").strip().lower()
                state = result.copy()
                if response == 'y':
                    state['approved'] = True
                app.update_state(config, state)
                has_checkpoint = True
            case _:
                print("✅ Workflow completed successfully:", result)
                keep_going = False

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

if __name__ == "__main__":
    # run_workflow(sys.argv[1] if len(sys.argv) > 1 else None)
    test_serializer()

