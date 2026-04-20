# APIRouter：创建路由子模块；Depends：依赖注入；HTTPException：抛出 HTTP 错误；status：HTTP 状态码常量
from fastapi import APIRouter, Depends, HTTPException, status
# Session：SQLAlchemy 数据库会话类型，用于 ORM 操作
from sqlalchemy.orm import Session

# User ORM 模型，映射数据库 users 表
from models.user import User
# 请求/响应 Pydantic Schema，用于入参校验和出参序列化
from schemas.User import (
    LoginRequest,       # 登录请求体：username + password
    LoginResponse,      # 登录响应体：message + access_token + token_type + user
    RegisterRequest,    # 注册请求体：username + password
    RegisterResponse,   # 注册响应体：message + user
    UserInfoResponse,   # 用户信息：id + username
)
# create_access_token：生成 JWT；get_current_user：从请求头解析 token 并返回当前用户
from utils.auth import create_access_token, get_current_user
# get_db：数据库会话依赖工厂，每次请求创建会话，请求结束后自动关闭
from utils.database import get_db
# hash_password：对明文密码做哈希；verify_password：验证明文与哈希是否匹配
from utils.password import hash_password, verify_password

# 创建路由，所有接口统一加 /auth 前缀，Swagger 文档分组为 "auth"
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
def register(
    payload: RegisterRequest, db: Session = Depends(get_db)
) -> RegisterResponse:
    """用户注册接口

    接收用户名和密码，校验用户名唯一性后创建新用户，返回用户基本信息。

    Args:
        payload (RegisterRequest): 请求体，包含 username（用户名）和 password（明文密码）
        db (Session): 由 FastAPI 依赖注入的数据库会话，无需手动传入

    Raises:
        HTTPException 400: 用户名已被注册

    Returns:
        RegisterResponse: 注册成功提示信息及新用户的 id、username
    """
    # 查询数据库中是否已存在同名用户
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        # 用户名重复，返回 400 拒绝注册
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在"
        )

    # 构造新用户对象，密码使用哈希存储，不保存明文
    new_user = User(
        username=payload.username, password_hash=hash_password(payload.password)
    )
    db.add(new_user)      # 将新用户加入当前数据库会话（尚未写入数据库）
    db.commit()           # 提交事务，正式写入数据库
    db.refresh(new_user)  # 刷新对象，使 new_user.id 等自动生成字段同步到内存

    # 用 model_validate 将 ORM 对象转换为 Pydantic Schema，再包装成响应体返回
    return RegisterResponse(
        message="注册成功", user=UserInfoResponse.model_validate(new_user)
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """用户登录接口

    验证用户名和密码，通过后签发 JWT access_token，客户端后续请求需在
    Authorization 请求头中携带 "Bearer <token>"。

    Args:
        payload (LoginRequest): 请求体，包含 username（用户名）和 password（明文密码）
        db (Session): 由 FastAPI 依赖注入的数据库会话，无需手动传入

    Raises:
        HTTPException 401: 用户名不存在或密码错误（故意合并提示，防止枚举攻击）

    Returns:
        LoginResponse: 登录成功提示、JWT token、token 类型及用户基本信息
    """
    # 按用户名查找用户，不存在则返回 None
    user = db.query(User).filter(User.username == payload.username).first()
    # 用户不存在 或 密码哈希不匹配，均返回 401（两种情况合并，避免泄露用户是否存在）
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误"
        )
    # 验证通过，为该用户签发 JWT access_token
    access_token = create_access_token(user.id, user.username)
    return LoginResponse(
        message="登陆成功",
        access_token=access_token,  # 返回给客户端，后续请求需放入 Authorization 头
        token_type="bearer",        # OAuth2 标准 token 类型
        user=UserInfoResponse.model_validate(user),
    )


@router.get("/me", response_model=UserInfoResponse)  # 修复：补全路径前导斜杠
def me(current_user: User = Depends(get_current_user)) -> UserInfoResponse:
    """获取当前登录用户信息接口

    从请求头 Authorization: Bearer <token> 中解析并验证 JWT，
    返回对应的用户基本信息。无需传入任何请求体。

    Args:
        current_user (User): 由 get_current_user 依赖注入，自动完成 token 解析和用户查询

    Raises:
        HTTPException 401: token 缺失、无效、过期，或对应用户不存在

    Returns:
        UserInfoResponse: 当前登录用户的 id 和 username
    """
    # 将 ORM User 对象转换为 Pydantic Schema 后返回
    return UserInfoResponse.model_validate(current_user)
