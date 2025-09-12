from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Interrupt
import sqlite3
import tempfile

import typing as t


# Define your graph state
class GraphState(t.TypedDict):
    query: str
    approved: bool

def do_something(dont_care_state) -> GraphState:
    print(f"Doing something: {dont_care_state}")
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

def run_workflow():
    # Build the graph
    workflow = StateGraph(GraphState)
    workflow.add_node("do_something", do_something)
    workflow.add_node("check_approval", check_for_approval)
    workflow.add_edge("do_something", "check_approval")
    workflow.set_entry_point("do_something")
    workflow.add_edge("check_approval", END) # Or to another node after approval

    # Create temporary SQLite database
    db_path = tempfile.mktemp(suffix=".db")
    print(f"📁 Using SQLite database: {db_path}")

    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Compile the graph with a checkpointer
    app = workflow.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "dynamic_interrupt_demo"}}

    keep_going = True
    state = {}
    while keep_going:
        result = app.invoke(state, config=config)
        match result:
            case {'approved': True}:
                print("✅ Workflow successful")
                # Continue to next node or finish
                keep_going = False
            case {'__interrupt__': [Interrupt(value=msg)]}:
                print(f"⚠️ Workflow interrupted: {msg}")
                response = input("Approve action? (y/n): ").strip().lower()
                state = result.copy()
                if response == 'y':
                    state['approved'] = True
                app.update_state(config, state)
                state = None
            case _:
                print("✅ Workflow completed successfully:", result)
                keep_going = False

if __name__ == "__main__":
    run_workflow()
