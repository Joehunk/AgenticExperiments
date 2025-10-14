from pydantic import BaseModel
from typing import Literal, TypeVar, Generic, TypedDict, Union

class Foo(BaseModel):
    field1: str

T = TypeVar('T', bound=BaseModel)

class Bar(BaseModel, Generic[T]):
    field2: T

bar = Bar[Foo](field2=Foo(field1="hello"))
dumped = bar.model_dump()
print(dumped)  # {'field2': {'field1': 'hello'}}

bar2 = Bar[Foo].model_validate(dumped)
print(bar2.field2.__class__.__name__)
assert bar == bar2

class Blat(BaseModel):
    blat_field: str
    
class Boom(BaseModel):
    boom_field: str

class Baz(BaseModel):
    field3: Union[Blat, Boom]
    
baz1 = Baz(field3=Blat(blat_field="world"))
dumped_baz1 = baz1.model_dump()
print(dumped_baz1)  # {'field3': {'blat_field': 'world'}}
baz1_reconstructed = Baz.model_validate(dumped_baz1)
assert baz1 == baz1_reconstructed
print (baz1_reconstructed.field3.__class__.__name__)  # Blat

# This only works because Boom and Blat have different field names
# Pydantic automatically determines which one to use based on the keys present
baz2 = Baz(field3=Boom(boom_field="universe"))
dumped_baz2 = baz2.model_dump()
print(dumped_baz2) 
baz2_reconstructed = Baz.model_validate(dumped_baz2)
print (baz2_reconstructed.field3.__class__.__name__) 
assert baz2 == baz2_reconstructed # Boom

# Let's try a sort of ad-hoc discriminated union with dictionaries
# which might sorta look like the way Davinix chunks things
class ChunkFoo(BaseModel):
    field: str

# Use the same name field to prevent Pydantic from using this to discriminate
# We want to show that the outer typed dictionary's field name is used.
class ChunkBar(BaseModel):
    field: int
    
class ChunkTypeFoo(TypedDict):
    foo: ChunkFoo

class ChunkTypeBar(TypedDict):
    bar: ChunkBar

class ChunkContainer(BaseModel):
    chunks: list[Union[ChunkTypeFoo, ChunkTypeBar]]
    
container = ChunkContainer(chunks=[{'foo': ChunkFoo(field='hello')}, {'bar': ChunkBar(field=42)}])
dumped_container = container.model_dump()
print(dumped_container)  # {'chunks': [{'foo': {'field': 'hello'}}, {'bar': {'field': 42}}]}
container_reconstructed = ChunkContainer.model_validate(dumped_container)
assert container == container_reconstructed
print(container_reconstructed.chunks[0]['foo'].__class__.__name__)  # ChunkFoo
print(container_reconstructed.chunks[1]['bar'].__class__.__name__)  # ChunkBar

# Let's pull the trigger a deeferent way
class ChunkedContainer2(BaseModel):
    chunks: list[Union[dict[Literal['foo'], ChunkFoo], dict[Literal['bar'], ChunkBar]]]
    
container2 = ChunkedContainer2(chunks=[{'foo': ChunkFoo(field='hello')}, {'bar': ChunkBar(field=42)}])
dumped_container2 = container2.model_dump()
print(dumped_container2)  # {'chunks': [{'foo': {'field': 'hello'}}, {'bar': {'field': 42}}]}
container2_reconstructed = ChunkedContainer2.model_validate(dumped_container2)
assert container2 == container2_reconstructed
print(container2_reconstructed.chunks[0]['foo'].__class__.__name__)  # ChunkFoo
print(container2_reconstructed.chunks[1]['bar'].__class__.__name__)  # ChunkBar
