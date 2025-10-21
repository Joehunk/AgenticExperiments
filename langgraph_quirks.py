from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import JsonPlusSerializer
from pydantic import BaseModel
from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

class Foo(BaseModel):
    foo_field: str
    
class Bar(BaseModel):
    bar_field: int
    
class Baz(BaseModel):
    baz_field: float
    
class Blat(BaseModel):
    blat_field: bool
    
def simple_linear_pydantic_graph() -> None:
    graph = StateGraph(state_schema=Foo, input_schema=Foo, output_schema=Blat)
    
    def first_node(state: Foo) -> Bar:
        return Bar(bar_field=len(state.foo_field))

    def second_node(state: Bar) -> Baz:
        return Baz(baz_field=float(state.bar_field) * 2.5)
    
    def final_node(state: Baz) -> Blat:
        return Blat(blat_field=state.baz_field > 10)

    graph.add_sequence([
        ("first_node", first_node),
        ("second_node", second_node),
        ("final_node", final_node),
    ])
    
    graph.set_entry_point("first_node")
    graph.add_edge("final_node", END)

    app = graph.compile(checkpointer=InMemorySaver(serde=JsonPlusSerializer()))
    result = app.invoke(input=Foo(foo_field="hello"), config={ "configurable": { "thread_id": "example_1"} })
    parsed_result = Blat.model_validate(result)
    print(f"Final result of simple linear graph: {parsed_result}")
    
def linear_pydantic_graph_with_crash_recovery() -> None:
    graph = StateGraph(state_schema=Foo, input_schema=Foo, output_schema=Blat)
    
    kaboom = False
    
    def first_node(state: Foo) -> Bar:
        print("First node executing")
        return Bar(bar_field=len(state.foo_field))

    def second_node(state: Bar) -> Baz:
        print("Second node executing")
        nonlocal kaboom
        if kaboom:
            raise RuntimeError("Simulated crash!")
        return Baz(baz_field=float(state.bar_field) * 2.5)
    
    def final_node(state: Baz) -> Blat:
        print("Final node executing")
        return Blat(blat_field=state.baz_field > 10)

    graph.add_sequence([
        ("first_node", first_node),
        ("second_node", second_node),
        ("final_node", final_node),
    ])
    
    graph.set_entry_point("first_node")
    graph.add_edge("final_node", END)

    app = graph.compile(checkpointer=InMemorySaver(serde=JsonPlusSerializer()))
    
    config: RunnableConfig = RunnableConfig(configurable={ "thread_id": "example_1"})
    # RunnableConfig is a TypedDict so this also works...
    config = { "configurable": { "thread_id": "example_1"} }
    
    try:
        kaboom = True
        app.invoke(input=Foo(foo_field="hello"), config=config)
    except RuntimeError as e:
        print(f"Caught expected error: {e}")
        
    # Note input=None. The checkpointer will restore the state.
    kaboom = False
    result = app.invoke(input=None, config=config)
    parsed_result = Blat.model_validate(result)
    print(f"Final result of simple linear graph: {parsed_result}")
    
def but_if_you_add_a_cycle():
    graph = StateGraph(state_schema=Foo, input_schema=Foo, output_schema=Blat)
    
    kaboom = False
    
    def first_node(state: Foo) -> Bar:
        print("First node executing")
        return Bar(bar_field=len(state.foo_field))

    def second_node(state: Bar) -> Baz:
        print("Second node executing")
        return Baz(baz_field=float(state.bar_field) * 2.5)
    
    def looping_node(state: Baz) -> Baz:
        print("Looping node executing")
        nonlocal kaboom
        if kaboom:
            raise RuntimeError("Simulated crash!")
        return Baz(baz_field=state.baz_field + 100)
    
    def final_node(state: Baz) -> Blat:
        print("Final node executing")
        return Blat(blat_field=state.baz_field > 1000)

    def check_if_loop(state: Baz) -> str:
        if state.baz_field < 1000:
            return "loop"
        return "continue"
    
    graph.add_sequence([
        ("first_node", first_node),
        ("second_node", second_node),
        ("looping_node", looping_node),
    ])
    graph.add_node("final_node", final_node)
    graph.add_conditional_edges("looping_node", check_if_loop, {
        "loop": "looping_node",
        "continue": "final_node",
    })
    
    
    graph.set_entry_point("first_node")
    graph.add_edge("final_node", END)

    app = graph.compile(checkpointer=InMemorySaver(serde=JsonPlusSerializer()))
    
    config: RunnableConfig = RunnableConfig(configurable={ "thread_id": "example_1"})
    
    # Running with no crash works fine
    result = app.invoke(input=Foo(foo_field="hello"), config=config)
    parsed_result = Blat.model_validate(result)
    print(f"Final result of simple linear graph (no crash): {parsed_result}")
    
    # Crashing does in fact crash as expected.
    try:
        print("Running with crash...")
        kaboom = True
        app.invoke(input=Foo(foo_field="hello"), config=config)
    except RuntimeError as e:
        print(f"Caught expected error: {e}")
    kaboom = False
        
    # But resuming not as much.
    kaboom = False
    print("Resuming after crash...")
    result = app.invoke(input=None, config=config)
    parsed_result = Blat.model_validate(result)
    print(f"Final result of simple linear graph: {parsed_result}")
    
if __name__ == "__main__":
    # simple_linear_pydantic_graph()
    # linear_pydantic_graph_with_crash_recovery()
    but_if_you_add_a_cycle()