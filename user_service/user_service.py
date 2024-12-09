from datetime import datetime
from fastapi import FastAPI, HTTPException, APIRouter, Depends
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from swipe_service.swipe_service import Swipe
from base import Base

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()
# FastAPI application
app = FastAPI()

# Add CORS middleware globally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

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

# Define a Pydantic model for the request body
class UpdateSwipesRequest(BaseModel):
    current_swipes: int

@app.get("/debug/routes")
def debug_routes():
    return [{"path": route.path, "methods": route.methods} for route in app.routes]

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
    try:
        swipe_records = [
            Swipe(
                donor_id=uni,
                created_date=datetime.utcnow()
            )
            for _ in range(current_swipes)
        ]
        print(f"Creating {len(swipe_records)} Swipe records for donor_id: {uni}")
        db.add_all(swipe_records)
        db.commit()
        print("Swipe records committed successfully")
    except Exception as e:
        db.rollback()
        print(f"Error during swipe creation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error initializing swipes: {str(e)}")

    return {"message": "User created successfully"}

@user_router.get("/users/{uni}")
def get_user(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# to account for both setting and incrementing/decrementing, is_relative
@user_router.put("/users/{uni}")
def update_user_swipes(
    uni: str, 
    request: UpdateSwipesRequest, 
    db: Session = Depends(get_db), 
    is_relative: bool = False  # Optional query parameter to decide mode
):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if is_relative:
        if request.current_swipes < 0 and abs(request.current_swipes) > user.current_swipes:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot decrement {abs(request.current_swipes)} swipes. User {uni} has only {user.current_swipes} swipes available."
            )
        user.current_swipes += request.current_swipes
        if request.current_swipes < 0:
            user.swipes_given += abs(request.current_swipes)
    else:
        # Handle absolute assignment
        if request.current_swipes < 0:
            raise HTTPException(status_code=400, detail="Swipe count cannot be negative")
        user.current_swipes = request.current_swipes

    db.commit()
    return {
        "message": f"Updated swipes for {uni}: current_swipes={user.current_swipes}, swipes_given={user.swipes_given}"
    }
# Include the user router in the FastAPI app
app.include_router(user_router, prefix="", tags=["Users"])

@app.get("/")
async def root():
    return {"message": "Welcome to the User Service!"}