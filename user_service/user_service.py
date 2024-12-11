from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, APIRouter, Depends
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import User, Swipe
from models.database import SessionLocal, initialize_database

initialize_database()

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
# engine = create_engine(DATABASE_URL, echo=True)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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

# Router for user-related endpoints
user_router = APIRouter()

# Define a Pydantic model for the request body
class UpdateUserAttributesRequest(BaseModel):
    current_swipes: Optional[int] = None  # Optional field with default None
    points: Optional[int] = None 

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
                uni=uni
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

  
class UserSchema(BaseModel):
    uni: str
    current_points: int = 0
    current_swipes: int = 0

    class Config:
        orm_mode = True

@app.post("/login")
def login_or_create_user(user: UserSchema):
    db = SessionLocal()
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.uni == user.uni).first()
        if existing_user:
            return {"message": "User exists", "user": existing_user}
        
        # Create new user if not found
        new_user = User(
            uni=user.uni,
            current_points=user.current_points,
            current_swipes=user.current_swipes,
        )
        db.add(new_user)
        db.commit()
        return {"message": "New user created", "user": new_user}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error processing request")
    finally:
        db.close()


@user_router.get("/users/{uni}")
def get_user(uni: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@user_router.put("/users/{uni}")
def update_user_attributes(
    uni: str, 
    request: UpdateUserAttributesRequest, 
    db: Session = Depends(get_db), 
    is_relative: bool = False
):
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update swipes
    if request.current_swipes is not None:
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
            if request.current_swipes < 0:
                raise HTTPException(status_code=400, detail="Swipe count cannot be negative")
            user.current_swipes = request.current_swipes

    # Update points
    if request.points is not None:
        if is_relative:
            if request.points < 0 and abs(request.points) > user.current_points:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot decrement {abs(request.points)} points. User {uni} has only {user.current_points} points available."
                )
            user.current_points += request.points
            if request.points < 0:
                user.points_given += abs(request.points)
        else:
            if request.points < 0:
                raise HTTPException(status_code=400, detail="Points count cannot be negative")
            user.current_points = request.points

    db.commit()
    return {
        "message": f"Updated attributes for {uni}: current_swipes={user.current_swipes}, swipes_given={user.swipes_given}, current_points={user.current_points}, points_given={user.points_given}"
    }


# # to account for both setting and incrementing/decrementing, is_relative
# @user_router.put("/users/{uni}")
# def update_user_attributes(
#     uni: str, 
#     request: UpdateUserAttributesRequest, 
#     db: Session = Depends(get_db), 
#     is_relative: bool = False  # Optional query parameter to decide mode
# ):
#     user = db.query(User).filter(User.uni == uni).first()
#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     if request.current_swipes:
#         if is_relative:
#             if request.current_swipes < 0 and abs(request.current_swipes) > user.current_swipes:
#                 raise HTTPException(
#                     status_code=400, 
#                     detail=f"Cannot decrement {abs(request.current_swipes)} swipes. User {uni} has only {user.current_swipes} swipes available."
#                 )
#             user.current_swipes += request.current_swipes
#             if request.current_swipes < 0:
#                 user.swipes_given += abs(request.current_swipes)
#         else:
#             # Handle absolute assignment
#             if request.current_swipes < 0:
#                 raise HTTPException(status_code=400, detail="Swipe count cannot be negative")
#             user.current_swipes = request.current_swipes
#     if request.points: 
#         if request.points < 0 and abs(request.points) > user.current_points:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Cannot decrement {abs(request.points)} points. User {uni} has only {user.current_points} points available."
#              )
#         else:
#             user.current_points += request.points
#     db.commit()
#     return {
#         "message": f"Updated attributes for {uni}: current_swipes={user.current_swipes}, swipes_given={user.swipes_given}, current_points = {user.current_points}, points_given = {user.points_given}"
#     }
# Include the user router in the FastAPI app
app.include_router(user_router, prefix="", tags=["Users"])

@app.get("/")
async def root():
    return {"message": "Welcome to the User Service!"}
