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

def workflow_test():
    def foo_to_bar_node(state: Foo) -> Bar:
        print(f"Converting Foo to Bar: {state}")
        return Bar(bar_field=len(state.foo_field))

    def bar_to_baz_node(state: Bar) -> Baz:
        print(f"Converting Bar to Baz: {state}")
        return Baz(baz_field=Bar(bar_field=state.bar_field))

    def baz_to_blat_node(state: Baz) -> Blat:
        print(f"Converting Baz to Blat: {state}")
        return Blat(blat_field=[str(state.baz_field.bar_field)] * state.baz_field.bar_field)
    
    graph = StateGraph(state_schema=dict, initial_schema=Foo, output_schema=Blat)
    
    graph.add_sequence(
        [
            ("foo_to_bar", foo_to_bar_node),
            ("bar_to_baz", bar_to_baz_node),
            ("baz_to_blat", baz_to_blat_node),
        ]
    )
    
    graph.set_entry_point("foo_to_bar")
    graph.add_edge("baz_to_blat", END)
    
    # compile graph with in-memory checkpointer
    checkpointer = InMemorySaver(serde=JsonPlusSerializer())
    app = graph.compile(checkpointer=checkpointer)
    
    result = app.invoke(Foo(foo_field="hello"), config={"configurable": {"thread_id": "test_run_1"}})
    parsed_result = Blat.model_validate(result)
    print(f"Final result: {parsed_result}")
    
workflow_test()