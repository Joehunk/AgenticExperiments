from pydantic import BaseModel, TypeAdapter
from typing import Literal, Union
from typing_extensions import Annotated
from pydantic import Field

class Foo(BaseModel):
    type: Literal['foo'] = 'foo'
    foo_prop: int

class Bar(BaseModel):
    type: Literal['bar'] = 'bar'
    bar_prop: str

# Create a discriminated union type
FooOrBar = Annotated[
    Union[Foo, Bar],
    Field(discriminator='type')
]

# Create a TypeAdapter for parsing
adapter = TypeAdapter(FooOrBar)

# Now you can parse your JSON!
some_json = {
    'type': 'bar',
    'bar_prop': 'wasup?'
}

result = adapter.validate_python(some_json)
print(result)  # Bar(type='bar', bar_prop='wasup?')
print(type(result))  # <class '__main__.Bar'>