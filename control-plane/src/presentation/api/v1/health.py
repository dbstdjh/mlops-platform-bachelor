from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db

router = APIRouter()


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    """Basic health check — verifies the API is running and the database is reachable."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
