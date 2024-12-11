import asyncio
from ariadne import QueryType, make_executable_schema, graphql_sync
from ariadne.asgi import GraphQL
from datetime import datetime
from fastapi import FastAPI, HTTPException, APIRouter, Depends, WebSocket
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import User, Swipe
from models.database import SessionLocal, initialize_database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

initialize_database()

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"

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

# GRAPHQL ENDPOINT IMPLEMENTATION -- READ ONLY
# Accessible through http://localhost:8001/graphql

# ----------------------------------------------
# Type Definitions
# ----------------------------------------------
type_defs = """
    type Query {
        users: [User]
        swipes: [Swipe]
    }

    type User {
        uni: String
        swipes_given: Int
        swipes_received: Int
        points_given: Int
        points_received: Int
        current_points: Int
        current_swipes: Int
    }

    type Swipe {
        swipe_id: Int
        uni: String
        is_donated: Boolean
    }
"""

# ----------------------------------------------
# Resolvers for queries
# ----------------------------------------------
query = QueryType()

@query.field("users")
def resolve_users(_, info):
    db = SessionLocal()
    users = db.query(User).all()
    db.close()
    return users

@query.field("swipes")
def resolve_swipes(_, info):
    db = SessionLocal()
    swipes = db.query(Swipe).all()
    db.close()
    return swipes

# ----------------------------------------------
# Create Executable Schema And Endpoint
# ----------------------------------------------
schema = make_executable_schema(type_defs, query)
app.add_route("/graphql", GraphQL(schema=schema))

# END OF GRAPHQL IMPLEMENTATION

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

@app.websocket("/ws/{uni}")
async def websocket_endpoint(uni: str, websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    while True:
        with SessionLocal() as fresh_session:
            user = fresh_session.query(User).filter(User.uni == uni).first()
            if user:
                data_json = {
                    "points_received": user.points_received,
                    "points_given": user.points_given,
                    "swipes_received": user.swipes_received,
                    "current_swipes": user.current_swipes,
                    "swipes_given": user.swipes_given,
                    "uni": user.uni,
                    "current_points": user.current_points,
                }
                await websocket.send_json(data_json)
            else:
                await websocket.send_json({"error": "User not found"})
                break
        await asyncio.sleep(1)

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

app.include_router(user_router, prefix="", tags=["Users"])

@app.get("/")
async def root():
    return {"message": "Welcome to the User Service!"}