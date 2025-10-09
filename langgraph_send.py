from time import sleep
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
    print(f"Processing item: {item}")
    sleep(1)  # Simulate some processing time
    print(f"Finished processing item: {item}")
    result = f"Processed: {item}"
    return {"results": [result]}

def run_graph():
    # Build the graph
    graph = StateGraph(State)
    graph.add_node("start", start_node)
    graph.add_conditional_edges("start", fan_out_node)
    graph.add_node("process_item", process_item)
    
    graph.set_entry_point("start")
    graph.add_edge("process_item", END)

    app = graph.compile()
    result = app.invoke(input={"items": ["item1", "item2", "item3"], "results": []},config={"configurable": {"thread_id": "fan_out_example"}, "max_concurrency": 1})
    print(result)
    
if __name__ == "__main__":
    run_graph()