from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

app = FastAPI()

# Database setup for AWS RDS MySQL
DATABASE_URL = "mysql+pymysql://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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

# Endpoints
@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db)
):
    # Verify that users exist
    donor = db.query(User).filter(User.uni == transaction.donor_id).first()
    recipient = db.query(User).filter(User.uni == transaction.recipient_id).first()
    if not donor or not recipient:
        raise HTTPException(status_code=404, detail="Donor or recipient not found")

    # Verify that the swipe exists and belongs to the donor
    swipe = db.query(SwipesToDonate).filter(
        SwipesToDonate.swipe_id == transaction.swipe_id,
        SwipesToDonate.donor_id == transaction.donor_id
    ).first()
    if not swipe:
        raise HTTPException(status_code=404, detail="Swipe not found or doesn't belong to donor")

    try:
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

        # Remove the swipe from swipes_to_donate
        db.delete(swipe)

        db.commit()
        db.refresh(db_transaction)
        return db_transaction
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/transactions", response_model=List[TransactionResponse])
def get_transactions(
    donor_id: Optional[str] = None,
    recipient_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Transaction)
    
    if donor_id:
        query = query.filter(Transaction.donor_id == donor_id)
    if recipient_id:
        query = query.filter(Transaction.recipient_id == recipient_id)
        
    return query.all()

@app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(Transaction).filter(Transaction.transaction_id == transaction_id).first()
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@app.get("/transactions/user/{uni}", response_model=List[TransactionResponse])
def get_user_transactions(uni: str, db: Session = Depends(get_db)):
    # Verify user exists
    user = db.query(User).filter(User.uni == uni).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return db.query(Transaction).filter(
        (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
    ).all()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)