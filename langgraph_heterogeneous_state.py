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

def adapt_input_node_to_channel[TIn: BaseModel, TOut: BaseModel](
    output_type: type[TOut],
    node: t.Callable[[TIn], TOut],
) -> t.Callable[[TIn], dict]:
    output_channel_name = channel_name_for_type(output_type)

    def wrapper(input_data: TIn) -> dict:
        output_data = node(input_data)
        return { output_channel_name: output_data.model_dump() }
    
    return wrapper

def adapt_output_node_to_channel[TIn: BaseModel, TOut: BaseModel](
    input_type: type[TIn],
    node: t.Callable[[TIn], TOut],
) -> t.Callable[[dict], TOut]:
    input_channel_name = channel_name_for_type(input_type)

    def wrapper(state: dict) -> TOut:
        input_data_raw = state.get(input_channel_name)
        if not input_data_raw:
            raise ValueError(f"Input channel '{input_channel_name}' is missing in state: {state}")
        input_data = input_type.model_validate(input_data_raw)
        output_data = node(input_data)
        return output_data
    
    return wrapper

def workflow_test():
    kaboom = False
    
    def foo_to_bar_node(state: Foo) -> Bar:
        print(f"Converting Foo to Bar: {state}")
        return Bar(bar_field=len(state.foo_field))
    
    def bar_to_generic_node(state: Bar) -> GenericClass[Bar]:
        print(f"Converting Bar to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=state)
    
    def generic_to_generic_node(state: GenericClass[Bar]) -> GenericClass[Bar]:
        print(f"Converting GenericClass[Bar] to GenericClass[Bar]: {state}")
        nonlocal kaboom
        if kaboom:
            raise ValueError("Kaboom! Intentional error for testing.")
        return GenericClass[Bar](item=Bar(bar_field=state.item.bar_field + 1))

    def generic_to_blat_node(state: GenericClass[Bar]) -> Blat:
        print(f"Converting GenericClass[Bar] to Blat: {state}")
        bar = state.item
        return Blat(blat_field=[str(bar.bar_field)] * bar.bar_field)
    
    def blat_to_baz_node(state: Blat) -> Baz:
        print(f"Converting Blat to Baz: {state}")
        bar = Bar(bar_field=len(state.blat_field))
        return Baz(baz_field=bar)
    
    subgraph = StateGraph(state_schema=dict)
    
    subgraph.add_sequence(
        [
            ("bar_to_generic", adapt_node_to_channel(Bar, GenericClass[Bar], bar_to_generic_node)),
            ("generic_to_generic", adapt_node_to_channel(GenericClass[Bar], GenericClass[Bar], generic_to_generic_node)),
            ("generic_to_blat", adapt_node_to_channel(GenericClass[Bar], Blat, generic_to_blat_node)),
        ]
    )
    subgraph.set_entry_point("bar_to_generic")
    subgraph.add_edge("generic_to_blat", END)

    graph = StateGraph(state_schema=dict)

    graph.add_sequence(
        [
            ("foo_to_bar", adapt_node_to_channel(Foo, Bar, foo_to_bar_node)),
            ("generic_processing", subgraph.compile(checkpointer=True)),
            ("blat_to_baz", adapt_node_to_channel(Blat, Baz, blat_to_baz_node)),
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