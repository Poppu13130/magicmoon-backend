# routers/items.py
from fastapi import APIRouter
from typing import Union

router = APIRouter(
    prefix="/items",          # les routes commenceront par /items
    tags=["items"],           # utile pour la doc Swagger
)

@router.get("/")
def read_items():
    return {"message": "Liste des items"}

@router.get("/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}
