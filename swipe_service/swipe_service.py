from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import requests

app = FastAPI()

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class SwipeToDonate(Base):
    __tablename__ = "Swipes_To_Donate"
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)
    donor_id = Column(String(50))
    created_date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

USER_SERVICE_URL = "http://localhost:8001"

@app.post("/swipes/donate")
def donate_swipe(donor_id: str):
    response = requests.get(f"{USER_SERVICE_URL}/users/{donor_id}")
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Donor not found")
    donor = response.json()
    if donor["current_swipes"] <= 0:
        raise HTTPException(status_code=400, detail="Not enough swipes available")

    db = SessionLocal()
    new_swipe = SwipeToDonate(donor_id=donor_id)
    db.add(new_swipe)
    db.commit()
    db.close()
    requests.post(f"{USER_SERVICE_URL}/users/{donor_id}", json={"current_swipes": donor["current_swipes"] - 1})
    return {"message": "Swipe donated successfully"}

@app.post("/swipes/claim")
def claim_swipe(recipient_id: str):
    db = SessionLocal()
    swipe = db.query(SwipeToDonate).first()
    if not swipe:
        db.close()
        raise HTTPException(status_code=400, detail="No swipes available")
    db.delete(swipe)
    db.commit()
    db.close()
    return {"message": "Swipe claimed successfully", "swipe_id": swipe.swipe_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)