from fastapi import APIRouter

from app.apis.recent import RecentOverallAPI
from app.schemas import EnabelRecent

router = APIRouter()


@router.post("/status/", summary="启用recent功能")
async def enableRecent(data: EnabelRecent):
    result = await RecentOverallAPI.enable_recent(data.platform, data.user_id, data.region, data.uid)
    return result

@router.delete("/status/", summary="取消recent_pro功能")
async def enableRecent(data: EnabelRecent):
    result = await RecentOverallAPI.disable_recent(data.platform, data.user_id, data.region, data.uid)
    return result