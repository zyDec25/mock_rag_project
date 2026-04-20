import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from utils.database import get_db
from models.user import User

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(user_id: int, username: str) -> str:
    # 计算 token 过期时间：当前 UTC 时间 + 配置的有效分钟数
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # 构造 JWT payload：sub 存用户 ID（JWT 标准字段），username 存用户名，exp 为过期时间
    payload = {"sub": str(user_id), "username": username, "exp": expire}

    # 使用密钥和 HS256 算法对 payload 进行签名编码，返回 JWT 字符串
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> dict:
    try:
        # 用密钥解码并验证 token，自动校验签名和过期时间；失败则抛出 JWTError
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # 从 payload 中取出用户 ID（存在 sub 字段中）
        user_id = payload.get("sub")
        if user_id is None:
            # sub 字段缺失，说明 token 结构不合法
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="无效登录态"
            )
        # 验证通过，返回完整 payload 供调用方使用
        return payload
    except JWTError:
        # 签名错误、token 篡改或已过期，均会触发此异常
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录态已失效，请重新登录"
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),  # FastAPI 自动从请求头提取 Bearer token
    db: Session = Depends(get_db),        # FastAPI 自动注入数据库会话
) -> User:
    # 先验证 token 合法性，返回解码后的 payload
    payload = verify_access_token(token)
    # 用 payload 中的用户 ID 查询数据库，获取对应的 User 记录
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        # token 合法但数据库中找不到该用户（可能已被删除）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
        )
    # 返回 User ORM 对象，供依赖此函数的路由直接使用
    return user
