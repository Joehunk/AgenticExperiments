from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from typing import TypedDict, Annotated
from operator import add

class State(TypedDict):
    items: list[str]
    results: Annotated[list[str], add]
    
def start_node(state: State):
    """This node initializes the items list"""
    return state # See if we can eliminate later.

def fan_out_node(state: State):
    """This node creates a Send for each item"""
    return [Send("process_item", {"item": item}) for item in state["items"]]

def process_item(state: dict):
    """This node processes a single item"""
    item = state["item"]
    # Do your processing here
    print("Untz")
    result = f"Processed: {item}"
    return {"results": [result]}

def run_graph():
    # Build the graph
    graph = StateGraph(State)
    graph.add_node("start", start_node)
    graph.add_conditional_edges("start", fan_out_node, ['process_item'])
    graph.add_node("process_item", process_item)
    
    graph.set_entry_point("start")
    graph.add_edge("process_item", END)

    app = graph.compile()
    result = app.invoke({"items": ["item1", "item2", "item3"], "results": []})
    print(result)
    
if __name__ == "__main__":
    run_graph()