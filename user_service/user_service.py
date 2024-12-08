from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./user_management.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    uni = Column(String, primary_key=True)
    swipes_given = Column(Integer, default=0)
    swipes_received = Column(Integer, default=0)
    points_given = Column(Integer, default=0)
    points_received = Column(Integer, default=0)
    current_points = Column(Integer, default=0)
    current_swipes = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

@app.post("/users")
def create_user(uni: str, current_points: int = 0, current_swipes: int = 0):
    db = SessionLocal()
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
    db.close()
    return {"message": "User created successfully"}

@app.get("/users/{uni}")
def get_user(uni: str):
    db = SessionLocal()
    user = db.query(User).filter(User.uni == uni).first()
    db.close()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/users/points/transfer")
def transfer_points(donor_id: str, recipient_id: str, points: int):
    db = SessionLocal()
    donor = db.query(User).filter(User.uni == donor_id).first()
    recipient = db.query(User).filter(User.uni == recipient_id).first()
    if not donor or donor.current_points < points:
        db.close()
        raise HTTPException(status_code=400, detail="Not enough points available")
    if not recipient:
        db.close()
        raise HTTPException(status_code=404, detail="Recipient not found")
    donor.current_points -= points
    donor.points_given += points
    recipient.current_points += points
    recipient.points_received += points
    db.commit()
    db.close()
    return {"message": "Points transferred successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
