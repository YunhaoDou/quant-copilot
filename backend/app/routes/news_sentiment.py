"""News-sentiment endpoint: recent headlines classified high/medium/low impact."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.redis_client import redis_client
from app.services import news_sentiment

router = APIRouter(prefix="/news", tags=["news_sentiment"])


class NewsSentimentRequest(BaseModel):
    symbol: str
    lang: str = "en"


@router.post("")
async def get_news_sentiment(req: NewsSentimentRequest):
    try:
        return await news_sentiment.get_news_sentiment(redis_client, req.symbol, lang=req.lang)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
