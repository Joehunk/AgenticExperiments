from time import sleep
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from typing import TypedDict, Annotated
from operator import add

from pydantic import BaseModel

class StartingState(BaseModel):
    chunks: int
    
class ChunkState(BaseModel):
    chunk_id: int
    
class AggregatedState(BaseModel):
    results: Annotated[list[int], add]
    
class ReducedState(BaseModel):
    summary: str
    
def start_node(state: StartingState):
    """This node initializes the items list"""
    return state # See if we can eliminate later.

def fan_out_node(state: StartingState):
    """This node creates a Send for each item"""
    return [Send("process_item", ChunkState(chunk_id=item)) for item in range(state.chunks)]

def process_item(state: ChunkState):
    """This node processes a single item"""
    print(f"Processing item: {state.chunk_id}")
    sleep(1)  # Simulate some processing time
    print(f"Finished processing item: {state.chunk_id}")
    return AggregatedState(results=[state.chunk_id * 2])

def reduce_states(state: AggregatedState):
    """This node reduces the results into a summary"""
    summary = f"Processed items: {', '.join(map(str, state.results))}"
    print(summary)
    return ReducedState(summary=summary)

def run_graph():
    # Build the graph
    graph = StateGraph(StartingState, None, input_schema=StartingState, output_schema=ReducedState)
    graph.add_node("start", start_node)
    graph.add_conditional_edges("start", fan_out_node)
    graph.add_node("process_item", process_item)
    graph.add_node("reduce_states", reduce_states)
    
    graph.set_entry_point("start")
    graph.add_edge("process_item", "reduce_states")
    graph.add_edge("reduce_states", END)

    app = graph.compile()
    result = app.invoke(input=StartingState(chunks=3), config={"configurable": {"thread_id": "fan_out_example"}, "max_concurrency": 1})
    print(result)
    
if __name__ == "__main__":
    run_graph()