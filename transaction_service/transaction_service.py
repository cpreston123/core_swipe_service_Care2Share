from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime
from typing import List
from pydantic import BaseModel
import logging

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

# Database Models - only what we need for transactions
class User(Base):
    __tablename__ = "Users"
    uni = Column(String(50), primary_key=True)
    swipes_given = Column(Integer, default=0)
    swipes_received = Column(Integer, default=0)
    current_swipes = Column(Integer, default=-1)

class Swipes(Base):
    __tablename__ = "Swipes"
    swipe_id = Column(Integer, primary_key=True, autoincrement=True)
    uni = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    is_donated = Column(Boolean, default=False)

class Transaction(Base):
    __tablename__ = "Transactions"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    swipe_id = Column(Integer, ForeignKey("Swipes.swipe_id"), nullable=False)
    donor_id = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    recipient_id = Column(String(50), ForeignKey("Users.uni"), nullable=False)
    transaction_date = Column(DateTime, default=datetime.utcnow)

# Pydantic Models for response formatting
class TransactionResponse(BaseModel):
    transaction_id: int
    donor_id: str
    recipient_id: str
    transaction_date: datetime

    class Config:
        orm_mode = True

class UserTransactionSummary(BaseModel):
    uni: str
    swipes_given: int
    swipes_received: int
    recent_transactions: List[TransactionResponse]

    class Config:
        orm_mode = True

# Database Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/transactions/history/{uni}", response_model=List[TransactionResponse])
def get_user_transaction_history(uni: str, limit: int = 10, db: Session = Depends(get_db)):
    """Get recent transaction history for a user (both donations and receipts)"""
    try:
        # Verify user exists
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # Get recent transactions where user was either donor or recipient
        transactions = db.query(Transaction).filter(
            (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
        ).order_by(Transaction.transaction_date.desc()).limit(limit).all()
        
        logger.info(f"Retrieved {len(transactions)} recent transactions for user: {uni}")
        return transactions
    except Exception as e:
        logger.error(f"Error getting transaction history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transactions/summary/{uni}", response_model=UserTransactionSummary)
def get_user_transaction_summary(uni: str, db: Session = Depends(get_db)):
    """Get user's transaction summary including total swipes given/received and recent transactions"""
    try:
        # Get user and their stats
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get 5 most recent transactions
        recent_transactions = db.query(Transaction).filter(
            (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
        ).order_by(Transaction.transaction_date.desc()).limit(5).all()

        return UserTransactionSummary(
            uni=user.uni,
            swipes_given=user.swipes_given,
            swipes_received=user.swipes_received,
            recent_transactions=recent_transactions
        )
    except Exception as e:
        logger.error(f"Error getting transaction summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)