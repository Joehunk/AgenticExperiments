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


class Foo(BaseModel):
    foo_field: str
    
class Bar(BaseModel):
    bar_field: int
    
class Baz(BaseModel):
    baz_field: Bar
    
class Blat(BaseModel):
    blat_field: list[str]
    
class GenericClass[T: BaseModel](BaseModel):
    item: T
    
def channel_name_for_type(t: type[BaseModel]) -> str:
    return f"channel_{t.__qualname__}"

def adapt_node_to_channel[TIn: BaseModel, TOut: BaseModel](
    input_type: type[TIn],
    output_type: type[TOut],
    node: t.Callable[[TIn], TOut],
) -> t.Callable[[dict], dict]:
    input_channel_name = channel_name_for_type(input_type)
    output_channel_name = channel_name_for_type(output_type)

    def wrapper(state: dict) -> dict:
        input_data_raw = state.get(input_channel_name)
        if not input_data_raw:
            raise ValueError(f"Input channel '{input_channel_name}' is missing in state: {state}")
        input_data = input_type.model_validate(input_data_raw)
        output_data = node(input_data)
        return { output_channel_name: output_data.model_dump() }
    
    return wrapper

def langgraph_pydantic_node[TIn: BaseModel, TOut: BaseModel](
    input_type: type[TIn],
    output_type: type[TOut],
) -> t.Callable[[t.Callable[[TIn], TOut]], t.Callable[[dict], dict]]:
    def decorator(node: t.Callable[[TIn], TOut]) -> t.Callable[[dict], dict]:
        return adapt_node_to_channel(input_type, output_type, node)
    return decorator

def workflow_test():
    kaboom = False
    
    @langgraph_pydantic_node(Foo, Bar)
    def foo_to_bar_node(state: Foo) -> Bar:
        print(f"Converting Foo to Bar: {state}")
        return Bar(bar_field=len(state.foo_field))
    
    @langgraph_pydantic_node(Bar, GenericClass[Bar])
    def bar_to_generic_node(state: Bar) -> GenericClass[Bar]:
        print(f"Converting Bar to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=state)

    @langgraph_pydantic_node(GenericClass[Bar], GenericClass[Bar])
    def generic_to_generic_node(state: GenericClass[Bar]) -> GenericClass[Bar]:
        print(f"Converting GenericClass[Bar] to GenericClass[Bar]: {state}")
        nonlocal kaboom
        if kaboom:
            raise ValueError("Kaboom! Intentional error for testing.")
        return GenericClass[Bar](item=Bar(bar_field=state.item.bar_field + 1))

    @langgraph_pydantic_node(GenericClass[Bar], Blat)
    def generic_to_blat_node(state: GenericClass[Bar]) -> Blat:
        print(f"Converting GenericClass[Bar] to Blat: {state}")
        bar = state.item
        return Blat(blat_field=[str(bar.bar_field)] * bar.bar_field)
    
    @langgraph_pydantic_node(Blat, Baz)
    def blat_to_baz_node(state: Blat) -> Baz:
        print(f"Converting Blat to Baz: {state}")
        bar = Bar(bar_field=len(state.blat_field))
        return Baz(baz_field=bar)
    
    subgraph = StateGraph(state_schema=dict)
    
    subgraph.add_sequence(
        [
            ("bar_to_generic", bar_to_generic_node),
            ("generic_to_generic", generic_to_generic_node),
            ("generic_to_blat", generic_to_blat_node),
        ]
    )
    subgraph.set_entry_point("bar_to_generic")
    subgraph.add_edge("generic_to_blat", END)

    graph = StateGraph(state_schema=dict)

    graph.add_sequence(
        [
            ("foo_to_bar", foo_to_bar_node),
            ("generic_processing", subgraph.compile(checkpointer=True)),
            ("blat_to_baz", blat_to_baz_node),
        ]
    )
    
    graph.set_entry_point("foo_to_bar")
    graph.add_edge("blat_to_baz", END)
    
    # compile graph with in-memory checkpointer
    checkpointer = InMemorySaver(serde=JsonPlusSerializer())
    app = graph.compile(checkpointer=checkpointer)
    
    config: RunnableConfig = {"configurable": {"thread_id": "test_run_1"}}
   
    kaboom = True
    try:
        app.invoke({ channel_name_for_type(Foo): Foo(foo_field="hello").model_dump() }, config=config)
        print("This should not print, as an error is expected.")
    except Exception as e:
        print(f"Caught an exception as expected: {e}")
    kaboom = False

    # invoke_func = adapt_node_to_channel(Foo, Baz, lambda input: app.invoke(input, config=config))

    # result = invoke_func(Foo(foo_field="hello"))
    
    result = app.invoke(None, config=config)
    print(f"Final result: {result}")

workflow_test()