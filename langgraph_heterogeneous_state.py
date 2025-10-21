from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.base import JsonPlusSerializer
from pydantic import BaseModel
from langgraph.graph import END, StateGraph
from langchain_core.runnables import RunnableConfig

import typing as t



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
    
def conditional_cyclic_workflow_test():
    # This blows up at the node that completes the cycle.
    @langgraph_pydantic_node(Foo, Bar)
    def before_loop_node(state: Foo) -> Bar:
        print(f"Converting Foo to Bar: {state}")
        return Bar(bar_field=len(state.foo_field))
    
    @langgraph_pydantic_node(Bar, GenericClass[Bar])
    def first_loop_node(state: Bar) -> GenericClass[Bar]:
        print(f"Converting Bar to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=state)
        
    @langgraph_pydantic_node(GenericClass[Bar], GenericClass[Bar])
    def second_loop_node(state: GenericClass[Bar]) -> GenericClass[Bar]:
        print(f"Converting GenericClass[Bar] to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=Bar(bar_field=state.item.bar_field - 1))

    @langgraph_pydantic_node(GenericClass[Bar], Bar)
    def third_loop_node(state: GenericClass[Bar]) -> Bar:
        return state.item
    
    def keep_looping(state: dict) -> str:
        bar = Bar.model_validate(state.get(channel_name_for_type(Bar)))
        if bar.bar_field > 0:
            return "loop"
        return "continue"
    
    @langgraph_pydantic_node(Bar, Foo)
    def after_loop_node(state: Bar) -> Foo:
        return Foo(foo_field=str(state.bar_field))
    
    graph = StateGraph(state_schema=dict)
    
    graph.add_sequence(
        [
            ("before_loop", before_loop_node),
            ("first_loop", first_loop_node),
            ("second_loop", second_loop_node),
            ("third_loop", third_loop_node),
        ]
    )
    
    graph.add_conditional_edges("third_loop", keep_looping, {
        "loop": "first_loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", after_loop_node)
    
    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ channel_name_for_type(Foo): Foo(foo_field="hello").model_dump() })
    print(f"Final result of cyclic workflow: {result}")
    
def conditional_cyclic_workflow_test_with_wrappers():
    # This also blows up so it's not the decorators.
    def before_loop_node(state: Foo) -> Bar:
        print(f"Converting Foo to Bar: {state}")
        return Bar(bar_field=len(state.foo_field))
    
    def first_loop_node(state: Bar) -> GenericClass[Bar]:
        print(f"Converting Bar to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=state)
        
    def second_loop_node(state: GenericClass[Bar]) -> GenericClass[Bar]:
        print(f"Converting GenericClass[Bar] to GenericClass[Bar]: {state}")
        return GenericClass[Bar](item=Bar(bar_field=state.item.bar_field - 1))

    def third_loop_node(state: GenericClass[Bar]) -> Bar:
        return state.item
    
    def keep_looping(state: Bar) -> bool:
        if state.bar_field > 0:
            return "loop"
        return "continue"
    
    def after_loop_node(state: Bar) -> Foo:
        return Foo(foo_field=str(state.bar_field))
    
    graph = StateGraph(state_schema=dict)
    
    graph.add_sequence(
        [
            ("before_loop", adapt_node_to_channel(Foo, Bar, before_loop_node)),
            ("first_loop", adapt_node_to_channel(Bar, GenericClass[Bar], first_loop_node)),
            ("second_loop", adapt_node_to_channel(GenericClass[Bar], GenericClass[Bar], second_loop_node)),
            ("third_loop", adapt_node_to_channel(GenericClass[Bar], Bar, third_loop_node)),
        ]
    )
    
    graph.add_conditional_edges("third_loop", keep_looping, {
        "loop": "first_loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", adapt_node_to_channel(Bar, Foo, after_loop_node))
    
    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ channel_name_for_type(Foo): Foo(foo_field="hello").model_dump() })
    print(f"Final result of cyclic workflow: {result}")
    
def conditional_cyclic_test_no_decorators():
    # This works
    graph = StateGraph(state_schema=dict)
    
    def before_loop(state: dict) -> dict:
        return { 'counter': int(state["counter_as_string"])}
    
    def count_down(state: dict) -> dict:
        return { 'counter': state["counter"] - 1 }

    def after_loop(state: dict) -> dict:
        return { 'summary': f"Final count is {state['counter']}" }
    
    def keep_looping(state: dict) -> str:
        if state["counter"] > 0:
            return "loop"
        return "continue"
    
    graph.add_sequence(
        [
            ("before_loop", before_loop),
            ("first_loop", count_down),
        ]
    )

    graph.add_conditional_edges("first_loop", keep_looping, {
        "loop": "first_loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", after_loop)

    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ "counter_as_string": "10" })
    print(f"Final result of simple cyclic workflow: {result}")
    
def conditional_cyclic_test_no_decorators_bigger():
    # This also works
    graph = StateGraph(state_schema=dict)
    
    def before_loop(state: dict) -> dict:
        return { 'counter': int(state["counter_as_string"])}
    
    def first_loop_node(state: dict) -> dict:
        return { 'counter_2': str(state["counter"]) }
    
    def second_loop_node(state: dict) -> dict:
        return { 'counter_3': int(state["counter_2"]) - 1 }
    
    def third_loop_node(state: dict) -> dict:
        print(f"Third loop node received state: {state}")
        return { 'counter': state["counter_3"] }

    def after_loop(state: dict) -> dict:
        return { 'summary': f"Final count is {state['counter']}" }
    
    def keep_looping(state: dict) -> str:
        if state["counter"] > 0:
            return "loop"
        return "continue"
    
    graph.add_sequence(
        [
            ("before_loop", before_loop),
            ("first_loop", first_loop_node),
            ("second_loop", second_loop_node),
            ("third_loop", third_loop_node),
        ]
    )

    graph.add_conditional_edges("third_loop", keep_looping, {
        "loop": "first_loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", after_loop)

    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ "counter_as_string": "5" })
    print(f"Final result of simple cyclic workflow: {result}")
    
def simplified_pydantic_with_decorators():
    # This blows up at the node that completes the cycle.
    @langgraph_pydantic_node(Foo, Bar)
    def before_loop_node(state: Foo) -> Bar:
        return Bar(bar_field=int(state.foo_field))
    
    @langgraph_pydantic_node(Bar, GenericClass[Bar])
    def loop_node(state: Bar) -> Bar:
        return Bar(bar_field=state.bar_field - 1)
        
    def keep_looping(state: Bar) -> bool:
        if state.bar_field > 0:
            return "loop"
        return "continue"
    
    @langgraph_pydantic_node(Bar, Foo)
    def after_loop_node(state: Bar) -> Foo:
        return Foo(foo_field=str(state.bar_field))
    
    graph = StateGraph(state_schema=dict)
    
    graph.add_sequence(
        [
            ("before_loop", before_loop_node),
            ("loop", loop_node),
        ]
    )

    graph.add_conditional_edges("loop", keep_looping, {
        "loop": "loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", after_loop_node)
    
    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ channel_name_for_type(Foo): Foo(foo_field="5").model_dump() })
    print(f"Final result of cyclic workflow: {result}")
    
def simplified_pydantic_manual():
    # This blows up at the node that completes the cycle.
    def before_loop_node(state: dict) -> dict:
        foo = Foo.model_validate(state["foo"])
        bar = Bar(bar_field=int(foo.foo_field))
        return { "bar": bar.model_dump() }
    
    def loop_node(state: dict) -> dict:
        bar = Bar.model_validate(state["bar"])
        return { "bar": Bar(bar_field=bar.bar_field - 1).model_dump() }

    def keep_looping(state: dict) -> str:
        bar = Bar.model_validate(state["bar"])
        if bar.bar_field > 0:
            return "loop"
        return "continue"
    
    # This is the problem. Apparently just changing the signature of
    # a function in add_conditional_edges makes it work.
    # If I change it to accept dict instead of Bar, it works.
    # It's obviously trying and failing to do some Pydantic magic.
    def keep_looping_this_blows_shit_up(state: Bar) -> str:
        if state.bar_field > 0:
            return "loop"
        return "continue"

    def after_loop_node(state: dict) -> dict:
        bar = Bar.model_validate(state["bar"])
        return { "foo": Foo(foo_field=str(bar.bar_field)).model_dump() }

    graph = StateGraph(state_schema=dict)
    
    graph.add_sequence(
        [
            ("before_loop", before_loop_node),
            ("loop", loop_node),
        ]
    )

    graph.add_conditional_edges("loop", keep_looping, {
        "loop": "loop",
        "continue": "after_loop",
    })
    graph.add_node("after_loop", after_loop_node)
    
    graph.set_entry_point("before_loop")
    graph.add_edge("after_loop", END)
    
    app = graph.compile()
    result = app.invoke({ "foo": Foo(foo_field="5").model_dump() })
    print(f"Final result of cyclic workflow: {result}")

conditional_cyclic_workflow_test()
