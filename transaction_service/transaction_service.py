from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./transaction_management.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    swipe_id = Column(Integer)
    donor_id = Column(String)
    recipient_id = Column(String)
    transaction_date = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

@app.post("/transactions")
def create_transaction(swipe_id: int, donor_id: str, recipient_id: str):
    db = SessionLocal()
    transaction = Transaction(swipe_id=swipe_id, donor_id=donor_id, recipient_id=recipient_id)
    db.add(transaction)
    db.commit()
    db.close()
    return {"message": "Transaction recorded successfully"}

@app.get("/transactions")
def get_transactions():
    db = SessionLocal()
    transactions = db.query(Transaction).all()
    db.close()
    return transactions

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
