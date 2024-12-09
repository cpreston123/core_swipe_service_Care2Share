from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware globally
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = "mysql+mysqlconnector://admin:care2share@care2share-db.clygygsmuyod.us-east-1.rds.amazonaws.com/care2share_database"
engine = create_engine(DATABASE_URL, echo=True)  # Set echo=True to debug queries
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "Users"
    uni = Column(String(50), primary_key=True)
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
        current_swipes=current_swipes
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
