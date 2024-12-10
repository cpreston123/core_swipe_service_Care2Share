from fastapi import FastAPI, HTTPException, Query
from more_itertools import consume
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import requests
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime
from base import Base  # Import the common Base


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()

class Swipe(Base):
    __tablename__ = "Swipes"  
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)  
    donor_id = Column(String(50), ForeignKey("Users.uni", ondelete="CASCADE"), nullable=False) 
    created_date = Column(DateTime, default=datetime.utcnow)  

class SwipeToDonate(Base):
    __tablename__ = "Swipes_To_Donate" #"Swipes"
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)
    donor_id = Column(String(50))
    #created_date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
USER_SERVICE_URL = "http://localhost:8002"

class DonateSwipeRequest(BaseModel):
    donor_id: str
    current_swipes: int
    is_relative: bool = True 
    
@app.post("/swipes/donate")
def donate_swipe(request: DonateSwipeRequest):
    try:
        donor_id = request.donor_id
        swipes = request.current_swipes  

        response = requests.get(f"http://localhost:8001/users/{donor_id}")
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Donor not found")
        donor = response.json()

        if donor["current_swipes"] < swipes:
            raise HTTPException(status_code=400, detail="Not enough swipes available")

        with SessionLocal() as db:
            try:
                swipes_to_add = [SwipeToDonate(donor_id=donor_id) for _ in range(swipes)]
                db.add_all(swipes_to_add)
                db.commit()
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

        update_response = requests.put(
            f"http://localhost:8001/users/{donor_id}",
            json={"current_swipes": -swipes},  
            params={"is_relative": "true"}  
        )
        if update_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to update swipe count")

        return {"message": f"{swipes} swipe(s) donated successfully"}
    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")



# @app.post("/swipes/donate")
# def donate_swipe(donor_id: str = Query(...)):
#     response = requests.get(f"{USER_SERVICE_URL}/users/{donor_id}")
#     if response.status_code != 200:
#         raise HTTPException(status_code=400, detail="Donor not found")
#     donor = response.json()
#     if donor["current_swipes"] <= 0:
#         raise HTTPException(status_code=400, detail="Not enough swipes available")

#     db = SessionLocal()
#     new_swipe = SwipeToDonate(donor_id=donor_id)
#     db.add(new_swipe)
#     db.commit()
#     db.close()
#     requests.post(f"{USER_SERVICE_URL}/users/{donor_id}", json={"current_swipes": donor["current_swipes"] - 1})
#     return {"message": "Swipe donated successfully"}

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

