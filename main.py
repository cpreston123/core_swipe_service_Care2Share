from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*']
)

# Database setup
DATABASE_URL = "sqlite:///./swipe_system.db"
engine = create_engine('mysql+pymysql://root:dbuserdbuser@localhost/care2share_database')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

try: 
    with engine.connect() as conn:
        result = conn.execute("SELECT 'HEllO, MYSQL!'")
        print(result.fetchone())
except Exception as e:
    print(f"Error: {e}")

# Models
class User(Base):
    __tablename__ = "users"
    uni = Column(String, primary_key=True)
    swipes_given = Column(Integer, default=0)
    swipes_received = Column(Integer, default=0)
    points_given = Column(Integer, default=0)
    points_received = Column(Integer, default=0)
    current_points = Column(Integer, default=0)
    current_swipes = Column(Integer, default=0)

class SwipeToDonate(Base):
    __tablename__ = "swipes_to_donate"
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)
    donor_id = Column(String, ForeignKey('users.uni'))
    created_date = Column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    swipe_id = Column(Integer, ForeignKey('swipes_to_donate.swipe_id'))
    donor_id = Column(String, ForeignKey('users.uni'))
    recipient_id = Column(String, ForeignKey('users.uni'))
    transaction_date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Pydantic schemas
class UserCreate(BaseModel):
    uni: str
    current_points: Optional[int] = 0
    current_swipes: Optional[int] = 0

class SwipeDonate(BaseModel):
    donor_id: str

class SwipeClaim(BaseModel):
    recipient_id: str

@app.post("/swipes/donate", response_model=dict)
def donate_swipe(swipe: SwipeDonate):
    db = SessionLocal()
    donor = db.query(User).filter(User.uni == swipe.donor_id).first()
    if not donor or donor.current_swipes <= 0:
        db.close()
        raise HTTPException(status_code=400, detail="Not enough swipes available")
    
    # Add swipe to outstanding swipes
    new_swipe = SwipeToDonate(donor_id=donor.uni)
    db.add(new_swipe)
    
    # Update donor stats
    donor.current_swipes -= 1
    donor.swipes_given += 1
    
    db.commit()
    db.close()
    return {"message": "Swipe donated successfully", "swipe_id": new_swipe.swipe_id}


@app.post("/swipes/claim", response_model=dict)
def claim_swipe(swipe: SwipeClaim):
    db = SessionLocal()
    recipient = db.query(User).filter(User.uni == swipe.recipient_id).first()
    if not recipient:
        db.close()
        raise HTTPException(status_code=404, detail="Recipient not found")
    
    # Check for outstanding swipes
    swipe_to_claim = db.query(SwipeToDonate).first()
    if not swipe_to_claim:
        db.close()
        raise HTTPException(status_code=400, detail="No swipes available to claim")
    
    # Complete the transaction
    transaction = Transaction(swipe_id=swipe_to_claim.swipe_id, donor_id=swipe_to_claim.donor_id, recipient_id=recipient.uni)
    db.add(transaction)
    
    # Remove swipe from outstanding pool
    db.delete(swipe_to_claim)
    
    # Update recipient stats
    recipient.swipes_received += 1
    
    db.commit()
    db.close()
    return {"message": "Swipe claimed successfully", "transaction_id": transaction.transaction_id}

@app.get("/swipes/outstanding", response_model=dict)
def get_outstanding_swipes():
    db = SessionLocal()
    outstanding_swipes = db.query(SwipeToDonate).all()
    db.close()
    return {"outstanding_swipes": [{"swipe_id": s.swipe_id, "donor_id": s.donor_id, "created_date": s.created_date} for s in outstanding_swipes]}

@app.post("/points/give", response_model=dict)
def give_points(data: dict):
    donor_id = data["donor_id"]
    recipient_id = data["recipient_id"]
    points = data["points"]

    db = SessionLocal()
    donor = db.query(User).filter(User.uni == donor_id).first()
    recipient = db.query(User).filter(User.uni == recipient_id).first()

    if not donor or donor.current_points < points:
        db.close()
        raise HTTPException(status_code=400, detail="Not enough points available")
    if not recipient:
        db.close()
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Transfer points
    donor.current_points -= points
    donor.points_given += points
    recipient.current_points += points
    recipient.points_received += points
    db.commit()
    db.close()
    return {"message": "Points transferred successfully"}

@app.post("/points/give", response_model=dict)
def give_points(data: dict):
    donor_id = data["donor_id"]
    recipient_id = data["recipient_id"]
    points = data["points"]

    db = SessionLocal()
    donor = db.query(User).filter(User.uni == donor_id).first()
    recipient = db.query(User).filter(User.uni == recipient_id).first()

    if not donor or donor.current_points < points:
        db.close()
        raise HTTPException(status_code=400, detail="Not enough points available")
    if not recipient:
        db.close()
        raise HTTPException(status_code=404, detail="Recipient not found")

    # Transfer points
    donor.current_points -= points
    donor.points_given += points
    recipient.current_points += points
    recipient.points_received += points
    db.commit()
    db.close()
    return {"message": "Points transferred successfully"}

@app.get("/")
async def root():
    return {"\n\nmessage": "Hello from core_swipe_service_Care2Share!\n\n"}


@app.get("/hello/{name}")
async def hello(name: str):
    msg = f"Hello {name} from core_swipe_service_Care2Share!"
    return {"\n\nmessage": msg}

swipes = {}
user_swipes = {}
user_points = {}

class Swipe(BaseModel):
    swipe_id: int
    donor_UNI: str
    user_UNI: str
    exchange_date: str

class UserSwipeUpdate(BaseModel):
    UNI: str
    num_of_swipes_given: int

class UserPointUpdate(BaseModel):
    UNI: str
    num_of_points_given: int

@app.post("/swipe/", response_model=Swipe)
async def create_swipe(swipe: Swipe):
    if swipe.swipe_id in swipes:
        raise HTTPException(status_code=400, detail="Swipe already exists")
    
    swipes[swipe.swipe_id] = swipe
    user_swipes[swipe.user_UNI] = user_swipes.get(swipe.user_UNI, 0) + 1
    user_swipes[swipe.donor_UNI] = user_swipes.get(swipe.donor_UNI, 0) - 1  
    return swipe


@app.get("/swipe/{swipe_id}")
async def get_swipe(swipe_id: int, include_details: bool = False):
    swipe = swipes.get(swipe_id)
    if not swipe:
        raise HTTPException(status_code=404, detail="Swipe not found")
    
    if include_details:
        user_swipe_info = user_swipes.get(swipe.user_UNI, "No data")
        donor_swipe_info = user_swipes.get(swipe.donor_UNI, "No data")
        swipe_data = {"swipe": swipe, "user_swipes": user_swipe_info, "donor_swipes": donor_swipe_info}
        return swipe_data
    return swipe

@app.put("/swipe/{swipe_id}", response_model=Swipe)
async def update_swipe(swipe_id: int, updated_swipe: Swipe):
    if swipe_id not in swipes:
        raise HTTPException(status_code=404, detail="Swipe not found")
    
    swipes[swipe_id] = updated_swipe
    return updated_swipe

@app.put("/user_points/update_async")
async def update_user_points_async(updates: UserPointUpdate):
    async def update_points(UNI: str, points: int):
        await asyncio.sleep(1)  
        if UNI in user_points:
            user_points[UNI]["num_of_points_given"] += points

    await asyncio.gather(update_points(updates.UNI, updates.num_of_points_given))
    return {"status": "User points are being updated asynchronously"}

# Endpoint to fetch a list of all swipes
@app.get("/swipes/")
async def get_all_swipes():
    return {"swipes": list(swipes.values())}

# An endpoint to fetch all swipes related to a specific user (UNI)
@app.get("/swipes/user/{UNI}")
async def get_user_swipes(UNI: str):
    user_related_swipes = [swipe for swipe in swipes.values() if swipe.user_UNI == UNI or swipe.donor_UNI == UNI]
    return {"user_swipes": user_related_swipes}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)



