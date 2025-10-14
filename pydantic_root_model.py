from pydantic import BaseModel, RootModel, Field
from typing import Literal, Union
from typing_extensions import Annotated

class Foo(BaseModel):
    type: Literal['foo'] = 'foo'
    foo_prop: int

class Bar(BaseModel):
    type: Literal['bar'] = 'bar'
    bar_prop: str

# Create a RootModel for your discriminated union
class FooOrBar(RootModel):
    # root: Annotated[
    #     Union[Foo, Bar],
    #     Field(discriminator='type')
    # ]
    root: Union[Foo, Bar]

# Now you can use it like a regular Pydantic model!
some_json = {
    'type': 'bar',
    'bar_prop': 'wasup?'
}

result = FooOrBar.model_validate(some_json)
print("Root model:")
print(result.root)  # Bar(type='bar', bar_prop='wasup?')
print(type(result.root))  # <class '__main__.Bar'>

# It has all the standard Pydantic model methods:
# FooOrBar.model_validate(...)
# FooOrBar.model_validate_json(...)
# FooOrBar.model_dump(...)
# etc.