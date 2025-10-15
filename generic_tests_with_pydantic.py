from pydantic import BaseModel

class Foo(BaseModel):
    field1: str

class Bar(BaseModel):
    field2: int

class Baz(BaseModel):
    field3: float

class ParentModel[T: BaseModel](BaseModel):
    child: T
    
def create_parent_with[T: BaseModel](child: T) -> ParentModel[T]:
    return ParentModel(child=child)

foo = create_parent_with(Foo(field1="test"))