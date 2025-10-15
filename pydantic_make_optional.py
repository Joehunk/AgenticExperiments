from typing import Optional, get_type_hints
from pydantic import BaseModel, create_model

def make_all_fields_optional(model_cls: type[BaseModel]) -> type[BaseModel]:
    """
    Return a new Pydantic model class with all fields made Optional,
    without modifying the original class.
    """
    # Resolve type hints (so ForwardRefs, etc. are handled)
    annotations = get_type_hints(model_cls, include_extras=True)
    new_fields = {}
    
    for name, field in model_cls.model_fields.items():
        field_type = annotations.get(name, field.annotation)
        new_fields[name] = (Optional[field_type], None)
    
    new_name = f"Optional{model_cls.__name__}"
    return create_model(new_name, __base__=model_cls.__base__, **new_fields)

class Foo(BaseModel):
    field1: str
    
try:
    Foo()
    print("this should not print")
except Exception as e:
    print(f"Error creating Foo without field1: {e}")

OptionalFoo = make_all_fields_optional(Foo)

o = OptionalFoo()
print(f"OptionalFoo created successfully: {o}")

o2 = OptionalFoo.model_validate({})
print(f"OptionalFoo created with empty dict: {o2}")
