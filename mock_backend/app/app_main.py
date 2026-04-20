from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from router.auth import router as auth_router
from router.knowledgebase import router as knowledgebase_router
from router.session import router as session_router
from utils.database import init_db
from utils.redis_client import close_redis

root_path = os.getenv("ROOT_PATH", "http://localhost:8000")

app = FastAPI(root_path=root_path)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源，生产环境中应该设置具体的源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

init_db()
app.include_router(auth_router)
app.include_router(knowledgebase_router)
app.include_router(session_router)


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_redis()

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

