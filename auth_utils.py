from jose import jwt, JWTError
from fastapi import HTTPException, Request
from decouple import config

SECRET_KEY = config("SECRET_KEY")  
ALGORITHM = "HS256"

def validate_jwt_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header is missing")

    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
