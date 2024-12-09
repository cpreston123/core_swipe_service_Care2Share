from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import logging
import random

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Database setup for AWS RDS MySQL with error handling
try:
    DATABASE_URL = "mysql+pymysql://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Test the connection
    with engine.connect() as conn:
        logger.info("Successfully connected to database!")
except Exception as e:
    logger.error(f"Failed to connect to database: {str(e)}")
    raise

Base = declarative_base()

# Database Models
class User(Base):
    __tablename__ = "Users"
    uni = Column(String(50), primary_key=True)
    swipes_given = Column(Integer, default=0)
    swipes_received = Column(Integer, default=0)
    points_given = Column(Integer, default=0)
    points_received = Column(Integer, default=0)
    current_points = Column(Integer, default=0)
    current_swipes = Column(Integer, default=0)

class UserSwipes(Base):
    __tablename__ = "User_Swipes"
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)
    uni = Column(String(50), ForeignKey("Users.uni"), nullable=False)

class SwipesToDonate(Base):
    __tablename__ = "Swipes_To_Donate"
    swipe_id = Column(Integer, ForeignKey("User_Swipes.swipe_id"), primary_key=True)
    donor_id = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    is_used = Column(Boolean, default=False)  # New column to track if swipe is used

class Transaction(Base):
    __tablename__ = "Transactions"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    swipe_id = Column(Integer, ForeignKey("Swipes_To_Donate.swipe_id"), nullable=False)
    donor_id = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    recipient_id = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    transaction_date = Column(DateTime, default=datetime.utcnow)

# Pydantic Models
class TransactionCreate(BaseModel):
    swipe_id: int
    donor_id: str
    recipient_id: str

class TransactionResponse(BaseModel):
    transaction_id: int
    swipe_id: int
    donor_id: str
    recipient_id: str
    transaction_date: datetime

    class Config:
        orm_mode = True

# Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db)
):
    try:
        # Verify that users exist
        donor = db.query(User).filter(User.uni == transaction.donor_id).first()
        recipient = db.query(User).filter(User.uni == transaction.recipient_id).first()
        if not donor or not recipient:
            raise HTTPException(status_code=404, detail="Donor or recipient not found")

        # Verify that the swipe exists, belongs to the donor, and hasn't been used
        swipe = db.query(SwipesToDonate).filter(
            SwipesToDonate.swipe_id == transaction.swipe_id,
            SwipesToDonate.donor_id == transaction.donor_id,
            SwipesToDonate.is_used == False
        ).first()
        if not swipe:
            raise HTTPException(status_code=404, detail="Swipe not found, doesn't belong to donor, or has already been used")

        # Create the transaction
        db_transaction = Transaction(
            swipe_id=transaction.swipe_id,
            donor_id=transaction.donor_id,
            recipient_id=transaction.recipient_id
        )
        db.add(db_transaction)

        # Update user statistics
        donor.swipes_given += 1
        donor.current_swipes -= 1
        recipient.swipes_received += 1
        recipient.current_swipes += 1

        # Mark the swipe as used instead of deleting it
        swipe.is_used = True

        db.commit()
        db.refresh(db_transaction)
        logger.info(f"Successfully created transaction: {db_transaction.transaction_id}")
        return db_transaction

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transactions/user/{uni}", response_model=List[TransactionResponse])
def get_user_transactions(uni: str, db: Session = Depends(get_db)):
    try:
        # Verify user exists
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        transactions = db.query(Transaction).filter(
            (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
        ).order_by(Transaction.transaction_date.desc()).all()
        
        logger.info(f"Retrieved {len(transactions)} transactions for user: {uni}")
        return transactions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transactions for user {uni}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)