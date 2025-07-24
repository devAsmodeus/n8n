from pydantic import BaseModel
from typing import Optional


class ResultResponse(BaseModel):
    error: bool
    message: Optional[str]
    results: Optional[dict]
