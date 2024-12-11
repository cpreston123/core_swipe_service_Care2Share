
import asyncio
from ariadne import QueryType, make_executable_schema, graphql_sync
from ariadne.asgi import GraphQL
from datetime import datetime
import logging
import os
import uuid
import base64
import json
import time
from typing import Optional
from contextvars import ContextVar
from urllib import response

from fastapi import FastAPI, HTTPException, APIRouter, Depends, Request, Response, status, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, Boolean, ForeignKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.mime.text import MIMEText

import contextvars
from decouple import config

# Import models and database initialization
from models import User, Swipe
from models.database import SessionLocal, initialize_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create context for correlation ID
correlation_id = contextvars.ContextVar('correlation_id', default=None)

# Correlation ID Middleware
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cor_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
        correlation_id.set(cor_id)
        
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = cor_id
        return response

# Authorization Middleware
class AuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cor_id = correlation_id.get()
        logger.info(f"CorrelationID: {cor_id} | Headers: {dict(request.headers)}")

        
        # List of public paths that don't require authorization
        # public_paths = ["/", "/docs", "/openapi.json", "/login", "/admin/users", "/admin/update-user"]
        
        # if request.url.path not in public_paths:
        #     auth_header = request.headers.get('Authorization')
        #     if not auth_header:
        #         logger.warning(f"CorrelationID: {cor_id} | Missing Authorization header for path: {request.url.path}")
        #         return JSONResponse(
        #             status_code=401,
        #             content={"detail": "Authorization header is missing"}
        #             )
                
        #     try:
        #         scheme, token = auth_header.split()
        #         if scheme.lower() != 'bearer' or not token:
        #             logger.warning(f"CorrelationID: {cor_id} | Invalid authorization scheme or missing token")
        #             return JSONResponse(
        #                 status_code=401,
        #                 content={"detail": "Invalid or missing authorization token"}
        #             )
        #     except ValueError:
        #         logger.warning(f"CorrelationID: {cor_id} | Malformed Authorization header")
        #         return JSONResponse(
        #             status_code=401,
        #             content={"detail": "Malformed Authorization header"}
        #             )
        response = await call_next(request)
        return response
        

# Logging Middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        cor_id = correlation_id.get()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"CorrelationID: {cor_id} | Path: {request.url.path} | Method: {request.method} | Time: {process_time:.4f}s")
        return response
    
initialize_database()

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"

# FastAPI application
app = FastAPI()

# OAuth 2.0 Configuration
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Path to credentials.json
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
CLIENT_ID = config("GOOGLE_CLIENT_ID")
CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET")
TOKEN_FILE = "token.json"  # Stores the user's access token

def get_gmail_service():
    """Authenticate using OAuth 2.0 and return Gmail API service."""
    creds = None

    # Load token.json if it exists
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as token:
            creds_data = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    # If no valid credentials, authenticate using credentials.json
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials to token.json
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_email(to, subject, message_text):
    """Send an email using Gmail API."""
    try:
        service = get_gmail_service()

        # Create email message
        message = MIMEText(message_text)
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw_message}

        # Use Gmail API to send the email
        service.users().messages().send(userId="me", body=body).execute()
        print(f"Email sent to {to}")
    except Exception as e:
        print(f"Error sending email: {e}")

# Add CORS middleware globally
# Add middleware
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(AuthorizationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

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
    current_points: int = -1
    current_swipes: int = -1

    class Config:
        orm_mode = True

class UpdateUserSchema(BaseModel):
    uni: str
    field: str  # 'current_points' or 'current_swipes'
    value: int

@user_router.post("/login", status_code=200)
def login_or_create_user(user: UserSchema, response: Response):
    db = SessionLocal()
    cor_id = correlation_id.get()
    try:
        # Check if user exists
        existing_user = db.query(User).filter(User.uni == user.uni).first()
        if existing_user:
            logger.info(f"CorrelationID: {cor_id} | User logged in: {user.uni}")
            return {"message": "User exists", "user": existing_user}
        
        # Create new user if not found
        new_user = User(
            uni=user.uni,
            current_points=user.current_points,
            current_swipes=user.current_swipes,
        )
        db.add(new_user)
        logger.info(f"CorrelationID: {cor_id} | New user created: {user.uni}")
        db.commit()

        # Send welcome email
        subject = "Welcome to Care2Share!"
        message_text = f"Hi {user.uni},\n\nWelcome to Care2Share! Currently, our admin is initializing your account. You will receive an email once your account is ready to begin donating / receiving swipes."
        send_email(user.uni, subject, message_text)

        response.status_code = status.HTTP_201_CREATED

        # Dynamically generate the URL for the new user using `url_for`
        # Assuming the route for fetching a user by their `uni` is named "get_user"
        print(new_user.uni)
        user_url = app.url_path_for("get_user", uni=new_user.uni)

        # Add the Link header with the URL of the newly created user resource
        response.headers["Link"] = f"<{user_url}>; rel='self'"
        return {"message": "New user created", "user": new_user}
    except Exception as e:
        db.rollback()
        logger.error(f"CorrelationID: {cor_id} | Error during login: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing request")
    finally:
        db.close()

@user_router.get("/users/{uni}")
def get_user(uni: str):
    cor_id = correlation_id.get()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.uni == uni).first()
        db.close()
        if not user:
            logger.warning(f"CorrelationID: {cor_id} | User not found: {uni}")
            raise HTTPException(status_code=404, detail="User not found")
        logger.info(f"CorrelationID: {cor_id} | Retrieved user: {uni}")
        return user
    except Exception as e:
        logger.error(f"CorrelationID: {cor_id} | Error retrieving user: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving user")

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

@app.get("/admin/users")
def get_all_users():
    db = SessionLocal()
    cor_id = correlation_id.get()
    try:
        users = db.query(User).all()
        if not users:
            logger.info(f"CorrelationID: {cor_id} | No users found")
            return {"message": "No users found", "users": []}
        
        # Convert users to a list of dictionaries to make it JSON serializable
        users_data = [
            {
                "uni": user.uni,
                "swipes_given": user.swipes_given,
                "swipes_received": user.swipes_received,
                "points_given": user.points_given,
                "points_received": user.points_received,
                "current_points": user.current_points,
                "current_swipes": user.current_swipes,
            }
            for user in users
        ]
        logger.info(f"CorrelationID: {cor_id} | Retrieved {len(users)} users")
        return {"message": "Users retrieved successfully", "users": users_data}
    except Exception as e:
        logger.error(f"CorrelationID: {cor_id} | Error retrieving users: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving users")
    finally:
        db.close()

@app.put("/admin/update-user", status_code=202)
def update_user(data: UpdateUserSchema, response: Response):
    db = SessionLocal()
    cor_id = correlation_id.get()
    try:
        user = db.query(User).filter(User.uni == data.uni).first()
        if not user:
            logger.warning(f"CorrelationID: {cor_id} | User not found: {data.uni}")
            raise HTTPException(status_code=404, detail="User not found")
        
        
        new_user = False
        if user.current_points == -1 or user.current_swipes == -1:
            new_user = True
        
        if data.field == "current_points":
            user.current_points = data.value

        elif data.field == "current_swipes":
            current_swipes = data.value
            if current_swipes < 0:
                logger.warning(f"CorrelationID: {cor_id} | Invalid swipe count for {data.uni}: {current_swipes}")
                raise HTTPException(
                    status_code=400, detail="Current swipes cannot be negative"
                )

            # Handle swipe logic
            existing_swipes = db.query(Swipe).filter(
                Swipe.uni == data.uni, Swipe.is_donated == False
            ).all()

            if len(existing_swipes) > current_swipes:
                to_delete = len(existing_swipes) - current_swipes
                for swipe in existing_swipes[:to_delete]:
                    db.delete(swipe)
            elif len(existing_swipes) < current_swipes:
                to_add = current_swipes - len(existing_swipes)
                for _ in range(to_add):
                    new_swipe = Swipe(uni=data.uni, is_donated=False)
                    db.add(new_swipe)

            user.current_swipes = current_swipes

        db.commit()
        
        
        if new_user and (user.current_swipes >= 0 and user.current_points >= 0):
            # Send New User Initialization email
            subject = "Care2Share - Account Initialized"
            message_text = f"Hi {user.uni},\n\nYour account has been initalized. You may now begin donating and receiving swipes! Your swipe count is {user.current_swipes} and your points count is {user.current_points}"
            send_email(user.uni, subject, message_text)
        
        logger.info(f"CorrelationID: {cor_id} | Updated user {data.uni}: {data.field} = {data.value}")
        return {"message": f"{data.field} updated successfully for {data.uni}"}
    except Exception as e:
        db.rollback()
        logger.error(f"CorrelationID: {cor_id} | Error updating user {data.uni}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        db.close()

app.include_router(user_router, prefix="", tags=["Users"])

@app.get("/")
async def root():
    return {"message": "Welcome to the User Service!"}