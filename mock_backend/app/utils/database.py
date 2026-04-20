from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
import os 
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """初始化数据库"""
    from models.user import User  # noqa: F401
    from models.session import Session  # noqa: F401
    from models.message import Message  # noqa: F401
    from models.document_upload import DocumentUpload  # noqa: F401
    from models.knowledgebase import KnowledgeBase  # noqa: F401

    Base.metadata.create_all(bind=engine)

