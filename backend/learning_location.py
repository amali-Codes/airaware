from pydantic import BaseModel


class Location(BaseModel):
    name: str
    latitude: float
    longitude: float


city = Location(
    name="Bengaluru",
    latitude=12.97,
    longitude=77.59
)


print(city.name)
print(city.latitude)