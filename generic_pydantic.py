from pydantic import BaseModel
from typing import TypeVar, Generic, Union

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