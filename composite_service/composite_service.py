from fastapi import FastAPI, HTTPException, Request
import httpx
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from swipe_service.swipe_service import DonatePointsRequest, DonateSwipeRequest, ReceivePointsRequest, ReceiveSwipeRequest
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this to a specific origin for production
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

USER_SERVICE_URL = "http://localhost:8001"  # Update with the actual user_service URL
TRANSACTION_SERVICE_URL = "http://localhost:8003"  # Update with the actual transaction_service URL
SWIPE_SERVICE_URL = "http://localhost:8002"  # Update with the actual swipe_service URL

@app.get("/user/{uni}/dashboard")
async def get_user_dashboard(uni: str):
    """
    Composite endpoint to fetch user details and transaction summary.
    """
    async with httpx.AsyncClient() as client:
        # Fetch user details
        user_response = await client.get(f"{USER_SERVICE_URL}/users/{uni}")
        if user_response.status_code != 200:
            raise HTTPException(status_code=user_response.status_code, detail="User service error")
        user_data = user_response.json()

        # Fetch transaction summary
        transaction_response = await client.get(f"{TRANSACTION_SERVICE_URL}/transactions/summary/{uni}")
        if transaction_response.status_code != 200:
            raise HTTPException(status_code=transaction_response.status_code, detail="Transaction service error")
        transaction_data = transaction_response.json()

    # Combine the data
    return {
        "user": user_data,
        "transaction_summary": transaction_data
    }

@app.post("/swipes/donate")
async def donate_swipes(donate_request: DonateSwipeRequest, request: Request):
    """
    Composite endpoint to handle swipe donations and create transactions.
    """
    donor_id = donate_request.donor_id
    swipes = donate_request.current_swipes 
    logger.info("donate request: %s", donate_request)
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": request.headers.get("Authorization")}
        
        response = await client.post(
            f"{SWIPE_SERVICE_URL}/swipes/donate",
            json=donate_request.model_dump(),
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Swipe service error")

    return {"message": f"{swipes} swipe(s) donated successfully"}

@app.post("/points/donate")
async def donate_swipes(donate_request: DonatePointsRequest, request: Request):
    """
    Composite endpoint to handle swipe donations and create transactions.
    """
    donor_id = donate_request.donor_id
    points = donate_request.points 
    logger.info("donate request: %s", donate_request)
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": request.headers.get("Authorization")}
        
        response = await client.post(
            f"{SWIPE_SERVICE_URL}/points/donate",
            json=donate_request.model_dump(),
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Swipe service error")

    return {"message": f"{points} swipe(s) donated successfully"}

@app.post("/swipes/claim")
async def claim_swipes(claim_request: ReceiveSwipeRequest, request: Request):
    """
    Composite endpoint to handle claiming swipes and create transactions.
    """
    recipient_id = claim_request.recipient_id
    swipes_to_claim = claim_request.swipes_to_claim 
    print(recipient_id)
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": request.headers.get("Authorization")}
        if not headers["Authorization"]:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        logger.info("Claim request: %s", claim_request)
        logger.info("headers: %s", headers)
        response = await client.post(
            f"{SWIPE_SERVICE_URL}/swipes/claim",
            json=claim_request.model_dump(),
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Swipe service error")
        claim_result = response.json()

        # Create a transaction for each claimed swipe
        for i in range(swipes_to_claim):
            response = await client.get(f"{SWIPE_SERVICE_URL}/swipes/donated")
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to retrieve donated swipes")
            
            # parse response data to get donated swipes
            response = response.json()
            donated_swipes = response["donated_swipes"]

            # Access the specific donated swipe
            swipe = donated_swipes[i]
            swipe_id = swipe["swipe_id"]
            donor_id = swipe["uni"]
            
            transaction_data = {
                "swipe_id": swipe_id,
                "donor_id": donor_id,
                "recipient_id": recipient_id,
                "transaction_date": claim_result.get("transaction_date")
            }
            transaction_response = await client.post(
                f"{TRANSACTION_SERVICE_URL}/transactions",
                json=transaction_data,
                params={
                    "uni": recipient_id
                },
                headers={"Authorization": request.headers.get("Authorization")}
            )
            if transaction_response.status_code != 200:
                raise HTTPException(status_code=transaction_response.status_code, detail="Transaction service error")

    return {"message": f"{swipes_to_claim} swipe(s) claimed successfully"}

@app.post("/points/claim")
async def claim_points(claim_request: ReceivePointsRequest, request: Request):
    """
    Composite endpoint to handle claiming points and create transactions.
    """
    recipient_id = claim_request.recipient_id
    points = claim_request.points 
    print(recipient_id)
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": request.headers.get("Authorization")}
        if not headers["Authorization"]:
            raise HTTPException(status_code=401, detail="Missing Authorization header")
        logger.info("Claim request: %s", claim_request)
        logger.info("headers: %s", headers)
        response = await client.post(
            f"{SWIPE_SERVICE_URL}/points/claim",
            json=claim_request.model_dump(),
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Swipe service error")

    return {"message": f"{points} point(s) claimed successfully"}

@app.get("/health")
def health_check():
    """Health check endpoint for the composite service."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
