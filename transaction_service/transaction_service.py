from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime
from typing import List
from pydantic import BaseModel
import logging
import time
import uuid
import contextvars

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create context for correlation ID
correlation_id = contextvars.ContextVar('correlation_id', default=None)

# Correlation ID Middleware
class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cor_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
        correlation_id.set(cor_id)
        
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = cor_id
        return response

# Authorization Middleware
class AuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cor_id = correlation_id.get()
        
        # List of paths that don't require authorization
        public_paths = ["/docs", "/openapi.json", "/redoc", "/favicon.ico"]
        
        if request.url.path not in public_paths:
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                logger.warning(f"CorrelationID: {cor_id} | No Authorization header present for path: {request.url.path}")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authorization header is missing"}
                )
                
            try:
                scheme, token = auth_header.split()
                if scheme.lower() != 'bearer':
                    logger.warning(f"CorrelationID: {cor_id} | Invalid authorization scheme: {scheme}")
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid authorization scheme. Expected 'Bearer'"}
                    )
                
                if not token:
                    logger.warning(f"CorrelationID: {cor_id} | No token provided")
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "No token provided"}
                    )
                    
            except ValueError:
                logger.warning(f"CorrelationID: {cor_id} | Invalid authorization header format")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authorization header format"}
                )
                
        response = await call_next(request)
        return response

# Logging Middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        cor_id = correlation_id.get()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"CorrelationID: {cor_id} | Path: {request.url.path} | Method: {request.method} | Time: {process_time:.4f}s")
        return response

# Error Handling Middleware
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            cor_id = correlation_id.get()
            logger.error(f"CorrelationID: {cor_id} | Global error handler caught: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )

# Header Middleware
class HeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Service-Name"] = "transaction-service"
        response.headers["X-Response-Time"] = str(time.time())
        return response

app = FastAPI()
security = HTTPBearer()

# Add all middleware in order
app.add_middleware(CorrelationIDMiddleware)  # First
app.add_middleware(AuthorizationMiddleware)  # Second
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(LoggingMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(HeaderMiddleware)

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

# Pydantic Models
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
def get_user_transaction_history(
    uni: str, 
    limit: int = 10, 
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent transaction history for a user (both donations and receipts)"""
    cor_id = correlation_id.get()
    try:
        # Verify user exists
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            logger.warning(f"CorrelationID: {cor_id} | User not found: {uni}")
            raise HTTPException(status_code=404, detail="User not found")
            
        # Get recent transactions where user was either donor or recipient
        transactions = db.query(Transaction).filter(
            (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
        ).order_by(Transaction.transaction_date.desc()).limit(limit).all()
        
        logger.info(f"CorrelationID: {cor_id} | Retrieved {len(transactions)} recent transactions for user: {uni}")
        return transactions
    except Exception as e:
        logger.error(f"CorrelationID: {cor_id} | Error getting transaction history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transactions/summary/{uni}", response_model=UserTransactionSummary)
def get_user_transaction_summary(
    uni: str, 
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get user's transaction summary including total swipes given/received and recent transactions"""
    cor_id = correlation_id.get()
    try:
        # Get user and their stats
        user = db.query(User).filter(User.uni == uni).first()
        if not user:
            logger.warning(f"CorrelationID: {cor_id} | User not found: {uni}")
            raise HTTPException(status_code=404, detail="User not found")

        # Get 5 most recent transactions
        recent_transactions = db.query(Transaction).filter(
            (Transaction.donor_id == uni) | (Transaction.recipient_id == uni)
        ).order_by(Transaction.transaction_date.desc()).limit(5).all()

        logger.info(f"CorrelationID: {cor_id} | Retrieved summary for user: {uni}")
        return UserTransactionSummary(
            uni=user.uni,
            swipes_given=user.swipes_given,
            swipes_received=user.swipes_received,
            recent_transactions=recent_transactions
        )
    except Exception as e:
        logger.error(f"CorrelationID: {cor_id} | Error getting transaction summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)