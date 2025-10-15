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
    
    subgraph = StateGraph(state_schema=Bar, initial_schema=Bar, output_schema=Bar)
    
    subgraph.add_sequence(
        [
            ("bar_to_generic", bar_to_generic_node),
            ("generic_to_generic", generic_to_generic_node),
            ("generic_to_blat", generic_to_blat_node),
        ]
    )
    subgraph.set_entry_point("bar_to_generic")
    subgraph.add_edge("generic_to_blat", END)
    
    graph = StateGraph(state_schema=Bar, initial_schema=Foo, output_schema=Baz)
    
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
        app.invoke(Foo(foo_field="hello"), config=config)
        print("This should not print, as an error is expected.")
    except Exception as e:
        print(f"Caught an exception as expected: {e}")
    kaboom = False

    result = app.invoke(None, config=config)
    parsed_result = Baz.model_validate(result)
    print(f"Final result: {parsed_result}")
    
workflow_test()