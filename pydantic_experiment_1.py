from pydantic import BaseModel, Field

class UniversalDict(dict):
    """A dict-like object that contains everything, recursively"""
    
    def __contains__(self, key):
        return True
    
    def __getitem__(self, key):
        # Return another UniversalDict for nested access
        return UniversalDict()
    
    def get(self, key, default=None):
        return UniversalDict()
    
    def keys(self):
        # Return an empty iterator since we can't iterate over everything
        return iter([])
    
    def items(self):
        return iter([])
    
    def values(self):
        return (UniversalDict() for _ in iter([]))
    
    def __bool__(self):
        return True
    
    def __len__(self):
        return float('inf')
    
    def __repr__(self):
        return "UniversalDict()"


class Address(BaseModel):
    street: str
    city: str
    postal_code: str = Field(exclude=True)

class User(BaseModel):
    name: str
    email: str
    address: Address

user = User(
    name="John",
    email="john@example.com",
    address=Address(street="123 Main St", city="NYC", postal_code="10001")
)

def get_all_inclusions():
    return UniversalDict()

# Normal serialization - postal_code is excluded
print(user.model_dump())
# {'name': 'John', 'email': 'john@example.com', 'address': {'street': '123 Main St', 'city': 'NYC'}}

# Override with exclude=set() - includes all fields, including nested excluded ones
print(user.model_dump(include={'address': {'postal_code': True, 'city': True}}, exclude=set()))

print(user.model_dump(round_trip=True))

user2 = User.model_validate(user.model_dump(round_trip=True))
