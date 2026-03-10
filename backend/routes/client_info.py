from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/client-ip")
async def get_client_ip(request: Request):
    ip = request.client.host if request.client else "unknown"
    return JSONResponse(content={"ip": ip})