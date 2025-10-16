from pydantic import BaseModel

class Foo(BaseModel):
    foo_field: str
    
class Bar[T: BaseModel](BaseModel):
    bar_field: T
    
foo_type: type[Foo] = Foo

def get_bar_of_type[T: BaseModel](t: type[T]) -> type[Bar[T]]:
    return Bar[t]

print(get_bar_of_type(Foo).__qualname__)