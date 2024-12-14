import logging
import contextvars
import uuid
import time
import os
import base64
import json

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.mime.text import MIMEText

from pydantic import BaseModel
from models import User, Swipe
from models.database import SessionLocal, initialize_database
from decouple import config

from jose import jwt, JWTError
from datetime import datetime, timedelta


# Secret key and algorithm for token encoding/decoding
SECRET_KEY = config("SECRET_KEY")
ALGORITHM = "HS256"

# Function to create an access token
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

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
        public_paths = ["/", "/docs", "/openapi.json", "/admin/login"]
        if request.url.path not in public_paths:
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(status_code=401, content={"detail": "Authorization token is missing or invalid"})

            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                request.state.user = payload  # Store user info in request state
            except JWTError:
                return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
        return await call_next(request)

        

# Logging Middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        cor_id = correlation_id.get()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"CorrelationID: {cor_id} | Path: {request.url.path} | Method: {request.method} | Time: {process_time:.4f}s")
        return response
    
DATABASE_URL = config("DATABASE_URL")

initialize_database()

USER_SERVICE_URL = "http://localhost:8004"

app = FastAPI()

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

# OAuth 2.0 Configuration
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = "token.json"

def get_gmail_service():
    """Authenticate using OAuth 2.0 and return Gmail API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as token:
            creds_data = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def send_email(to, subject, message_text):
    """Send an email using Gmail API."""
    try:
        service = get_gmail_service()
        message = MIMEText(message_text)
        message["to"] = to
        message["subject"] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {"raw": raw_message}
        service.users().messages().send(userId="me", body=body).execute()
    except Exception as e:
        print(f"Error sending email: {e}")

class UpdateUserSchema(BaseModel):
    uni: str
    field: str  # 'current_points' or 'current_swipes'
    value: int

class LoginSchema(BaseModel):
    username: str
    password: str

@app.post("/admin/login")
def login(data: LoginSchema):
    if data.username == "admin" and data.password == "care2share":  # Replace with actual database logic
        token = create_access_token(data={"sub": data.username})
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid username or password")


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