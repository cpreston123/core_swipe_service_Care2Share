from fastapi import FastAPI, HTTPException, Query
from more_itertools import consume
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import requests
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from models import Swipe, User, Transaction, Points
from models.database import SessionLocal

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

@app.post("/swipes/donate")
def donate_swipe(request: DonateSwipeRequest):
    donor_id = request.donor_id
    swipes = request.current_swipes  

    response = requests.get(f"http://localhost:8001/users/{donor_id}")
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
            if not swipe_to_update:
                raise HTTPException(status_code=400, detail="No available swipes to donate")
            
            swipe_to_update.is_donated = True
            db.add(swipe_to_update)

        db.commit()
    update_response = requests.put(
        f"http://localhost:8001/users/{donor_id}",
        json={"current_swipes": -swipes},
        params={"is_relative": True}  
    )
    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update swipe count")

    return {"message": f"{swipes} swipe(s) donated successfully"}

@app.post("/swipes/claim")
def claim_swipe(recipient_id: str):
    with SessionLocal() as db:
        swipe = db.query(Swipe).filter(Swipe.is_donated == True).first()
        if not swipe:
            raise HTTPException(status_code=400, detail="No swipes available to claim")

        recipient = db.query(User).filter(User.uni == recipient_id).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient not found")

        donor_id = swipe.uni  
        swipe.is_donated = False
        swipe.uni = recipient_id

        transaction = Transaction(
            swipe_id=swipe.swipe_id,
            donor_id=donor_id,
            recipient_id=recipient_id,
            transaction_date=datetime.utcnow()
        )
        db.add(transaction)
        db.commit()

    donor_update_response = requests.put(
        f"http://localhost:8001/users/{donor_id}",
        json={"swipes_given": 1},
        params={"is_relative": "true"}
    )
    recipient_update_response = requests.put(
        f"http://localhost:8001/users/{recipient_id}",
        json={"current_swipes": 1, "swipes_received": 1},
        params={"is_relative": "true"}
    )

    if donor_update_response.status_code != 200 or recipient_update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update donor or recipient")

    return {"message": "Swipe claimed successfully", "swipe_id": swipe.swipe_id}

@app.post("/points/donate")
def donate_points(request: DonatePointsRequest):
    donor_id = request.donor_id
    points_to_donate = request.points

    # Fetch donor information
    response = requests.get(f"http://localhost:8001/users/{donor_id}")
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
        params={"is_relative": "true"}
    )
    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update donor's points")

    return {"message": f"{points_to_donate} point(s) donated successfully"}

@app.post("/points/claim")
def claim_points(recipient_id: str, points: int):
    with SessionLocal() as db:
        recipient = db.query(User).filter(User.uni == recipient_id).first()
        if not recipient:
            raise HTTPException(status_code=404, detail="Recipient not found")

        points_row = db.query(Points).first()
        if not points_row or points_row.points < points:
            raise HTTPException(status_code=400, detail="Not enough points available to claim")

        points_row.points -= points
        db.commit()  # Save changes to the global points table

    update_response = requests.put(
        f"http://localhost:8001/users/{recipient_id}",
        json={"points": points, "points_received": points},
        params={"is_relative": "true"}  # Indicate this is a relative update
    )

    if update_response.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to update recipient's points")

    return {"message": f"{points} point(s) claimed successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

