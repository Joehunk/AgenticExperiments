from pydantic import BaseModel, Field
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

class GenericBase[T: BaseModel | list[BaseModel]](BaseModel):
    item: T

def create_generic_model_instance[T: BaseModel | list[BaseModel]](model_cls: type[T], list_size: int | None = None) -> type:
    if list_size is not None:
        field_kwargs = {'min_length': list_size, 'max_length': list_size}
    else:
        field_kwargs = {}
    class GenericModel(GenericBase[model_cls]):
        item: model_cls = Field(..., **field_kwargs) # type: ignore

    return GenericModel

generic_model = create_generic_model_instance(Foo)
instance = generic_model(item=Foo(field1="generic"))
dumped_instance = instance.model_dump()
print(dumped_instance)  # {'item': {'field1': 'generic'}}
reconstructed_instance = generic_model.model_validate(dumped_instance)
print(reconstructed_instance.item.__class__.__name__)  # Foo

generic_model = create_generic_model_instance(list[Foo], list_size=2)
instance = generic_model(item=[Foo(field1="one"), Foo(field1="two")])
dumped_instance = instance.model_dump()
print(dumped_instance)  # {'item': [{'field1': 'one'}, {'field1': 'two'}]}
reconstructed_instance = generic_model.model_validate(dumped_instance)
print([foo.__class__.__name__ for foo in reconstructed_instance.item])  # ['Foo

try:
    invalid_instance = generic_model(item=[Foo(field1="only one")])
    print("This should not print")
except Exception as e:
    print(f"Error as expected for invalid list size: {e}")
    
print(f"Name of ungeneric type: {GenericBase.__name__}")
print(f"Name of generic type: {GenericBase[Foo].__name__}")