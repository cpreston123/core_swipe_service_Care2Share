from fastapi import FastAPI, HTTPException, Query, Depends, Request
from more_itertools import consume
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import requests
import os
import json
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import Swipe, User, Transaction, Points
from models.database import SessionLocal
from decouple import config
from auth_utils import validate_jwt_token

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"

USER_SERVICE_URL = "http://localhost:8002"

class DonateSwipeRequest(BaseModel):
    donor_id: str
    current_swipes: int
    is_relative: bool = True 

class DonatePointsRequest(BaseModel):
    donor_id: str
    points: int

class ReceiveSwipeRequest(BaseModel):
    recipient_id: str
    swipes_to_claim: int

class ReceivePointsRequest(BaseModel):
    recipient_id: str
    points: int

# OAuth 2.0 Configuration
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = "token.json"

# Authorization Middleware
SECRET_KEY = config("SECRET_KEY")  # Same secret key used in login microservice
ALGORITHM = "HS256" 

def jwt_dependency(request: Request):
    auth_header = request.headers.get("Authorization")
    try:
        return validate_jwt_token(auth_header, SECRET_KEY)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

def get_gmail_service():
    """Authenticate using OAuth 2.0 and return Gmail API service."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as token:
            creds_data = json.load(token)
            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
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

@app.post("/swipes/donate")
def donate_swipe(request: Request, donate_request: DonateSwipeRequest, user_info: dict = Depends(validate_jwt_token)):
    donor_id = donate_request.donor_id
    swipes = donate_request.current_swipes  
    print(f"Authorization passed for donor: {donor_id}, swipes: {swipes}")

    if user_info.get("sub") != donor_id:
        raise HTTPException(
            status_code=403, detail="You are not authorized to donate on behalf of this user"
        )

    # Forward the Authorization header to the /users endpoint
    auth_header = request.headers.get("Authorization")
    print('auth_header', auth_header)
    response = requests.get(
        f"http://localhost:8001/users/{donor_id}",
        headers={"Authorization": auth_header}
    )
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Donor not found")
    donor = response.json()

    if donor["current_swipes"] < swipes:
        raise HTTPException(status_code=400, detail="Not enough swipes available")
    with SessionLocal() as db:
        for _ in range(swipes):
            swipe_to_update = db.query(Swipe).filter(
                Swipe.uni == donor_id,
                Swipe.is_donated == False
            ).first()
            print(swipe_to_update)
            if not swipe_to_update:
                raise HTTPException(status_code=400, detail="No available swipes to donate")
            
            swipe_to_update.is_donated = True
            db.add(swipe_to_update)
            db.commit()

        db.commit()
    update_response = requests.put(
        f"http://localhost:8001/users/{donor_id}",
        json={"current_swipes": -swipes},
        params={"is_relative": True},
        headers={"Authorization": auth_header} 
    )
    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update swipe count")
    
    # Send email notification
    subject = "Thank You for Donating Swipes!"
    message_text = f"Hi {donor_id},\n\nThank you for donating {swipes} swipe(s). Your generosity is greatly appreciated!"
    send_email(donor["uni"], subject, message_text)

    return {"message": f"{swipes} swipe(s) donated successfully"}

@app.post("/swipes/claim")
def claim_swipe(request: Request, claim_request: ReceiveSwipeRequest, user_info: dict = Depends(validate_jwt_token)):
    recipient_id = claim_request.recipient_id
    swipes_to_claim = claim_request.swipes_to_claim 

    if user_info.get("sub") != recipient_id:
        raise HTTPException(
            status_code=403, detail="You are not authorized to claim swipes for this user"
        )

    # Access the Authorization header from the HTTP request
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    
    with SessionLocal() as db:
        donated_swipes = db.query(Swipe).filter(Swipe.is_donated == True).all()
        if len(donated_swipes) < swipes_to_claim:
            raise HTTPException(status_code=400, detail="No swipes available to claim")

        for i in range(swipes_to_claim):
            swipe = donated_swipes[i]
            swipe_id = swipe.swipe_id
            print(swipe_id)
            recipient = db.query(User).filter(User.uni == recipient_id).first()
            if not recipient:
                raise HTTPException(status_code=404, detail="Recipient not found")

            donor_id = swipe.uni
            swipe.is_donated = False
            swipe.uni = recipient_id
            recipient.swipes_received += 1
            transaction = Transaction(
                swipe_id=swipe_id,
                donor_id=donor_id,
                recipient_id=recipient_id,
                transaction_date=datetime.utcnow()
            )
            db.add(transaction)
            db.commit()
            donor_update_response = requests.put(
                f"http://localhost:8001/users/{donor_id}",
                json={"swipes_given": 1},
                params={"is_relative": "true"},
                headers={"Authorization": auth_header}  
            )
            recipient_update_response = requests.put(
                f"http://localhost:8001/users/{recipient_id}",
                json={"current_swipes": 1, "swipes_received": 1},
                params={"is_relative": "true"},
                headers={"Authorization": auth_header}
            )
            print(donor_update_response, recipient_update_response)
            if donor_update_response.status_code != 200 or recipient_update_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to update donor or recipient statuses")
            
        subject = "Swipe Claim Successful!"
        message_text = f"Hi {recipient_id},\n\nYou have successfully claimed {swipes_to_claim} swipe(s). Enjoy your meal!"
        send_email(recipient.uni, subject, message_text)

        return {"message": f"{swipes_to_claim} swipe(s) claimed successfully", "swipe_id": swipe_id}

@app.post("/points/donate")
def donate_points(request: Request, donate_request: DonatePointsRequest, user_info: dict = Depends(validate_jwt_token)):
    donor_id = donate_request.donor_id
    points_to_donate = donate_request.points

    if user_info.get("sub") != donor_id:
        raise HTTPException(
            status_code=403, detail="You are not authorized to donate on behalf of this user"
        )

    # Access the Authorization header from the HTTP request
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header is missing")

    # Fetch donor information
    print(auth_header)
    response = requests.get(
        f"http://localhost:8001/users/{donor_id}",
        headers={"Authorization": auth_header}
    )
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Donor not found")
    donor = response.json()

    if donor["current_points"] < points_to_donate:
        raise HTTPException(status_code=400, detail="Not enough points available")

    with SessionLocal() as db:
        points_row = db.query(Points).first()
        if not points_row:
            points_row = Points(points=0)  # Initialize if the table is empty
            db.add(points_row)
        
        points_row.points += points_to_donate
        db.commit()

    # Update donor's points using the centralized function
    update_response = requests.put(
        f"http://localhost:8001/users/{donor_id}",
        json={"points": -points_to_donate, "points_given": points_to_donate},
        params={"is_relative": "true"},
        headers={"Authorization": auth_header}
    )
    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update donor's points")

    return {"message": f"{points_to_donate} point(s) donated successfully"}

@app.post("/points/claim")
def claim_points(request: Request, claim_request: ReceivePointsRequest, user_info: dict = Depends(validate_jwt_token)):
    if user_info.get("sub") != claim_request.recipient_id:
        raise HTTPException(
            status_code=403, detail="You are not authorized to claim points for this user"
        )

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    
    with SessionLocal() as db:
        recipient = db.query(User).filter(User.uni == claim_request.recipient_id).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient not found")

        points_row = db.query(Points).first()
        if not points_row or points_row.points < claim_request.points:
            raise HTTPException(status_code=400, detail="Not enough points available to claim")

        recipient.points_received += claim_request.points
        points_row.points -= claim_request.points
        db.commit()  

    update_response = requests.put(
        f"http://localhost:8001/users/{claim_request.recipient_id}",
        json={"points": claim_request.points, "points_received": claim_request.points},
        params={"is_relative": "true"},
        headers={"Authorization": auth_header}  
    )

    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update recipient's points")

    return {"message": f"{claim_request.points} point(s) claimed successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
