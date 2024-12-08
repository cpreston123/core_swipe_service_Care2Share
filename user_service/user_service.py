from fastapi import FastAPI, HTTPException, APIRouter, Depends
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL, echo=True)
# Set echo=True to debug queries
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# FastAPI application
app = FastAPI()

# Dependency for database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Database model
class User(Base):
    __tablename__ = "Users"
    uni = Column(String(50), primary_key=True)
    swipes_given = Column(Integer, default=0)
    swipes_received = Column(Integer, default=0)
    points_given = Column(Integer, default=0)
    points_received = Column(Integer, default=0)
    current_points = Column(Integer, default=0)
    current_swipes = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

# Router for user-related endpoints
user_router = APIRouter()

@user_router.post("/users")
def create_user(uni: str, current_points: int = 0, current_swipes: int = 0, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if user:
        raise HTTPException(status_code=400, detail="User already exists")
    new_user = User(
        uni=uni,
        current_points=current_points,
        current_swipes=current_swipes,
    )
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}

@user_router.get("/users/{uni}")
def get_user(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# Include the user router in the FastAPI app
app.include_router(user_router, prefix="", tags=["Users"])

@app.get("/")
async def root():
    return {"message": "Welcome to the User Service!"}