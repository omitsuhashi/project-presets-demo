from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel

app = FastAPI()


class Health(BaseModel):
    ok: bool


@app.get("/health")
async def health(verbose: Annotated[bool, Query()] = False) -> Health:
    return Health(ok=True)
