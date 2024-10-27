from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic import BaseModel
import asyncio

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*']
)

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



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)



