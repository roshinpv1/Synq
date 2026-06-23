import os
import base64
import hashlib
import hmac
import json
import time
import secrets
from typing import Dict, Any, Optional
from fastapi import Header, HTTPException, status, Depends

SECRET_KEY = os.environ.get("SYNQ_JWT_SECRET", "super-secret-synq-commercial-token-key-change-in-prod")
ALGORITHM = "HS256"
# Tokens expire in 1 day by default
DEFAULT_EXPIRE_SECONDS = 86400

def get_password_hash(password: str, salt: str = None) -> tuple[str, str]:
    """Hash password using PBKDF2 with SHA-256 and return (hashed_password, salt)."""
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_bytes = password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hashed = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
    return base64.b64encode(hashed).decode('utf-8'), salt

def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    """Verify a plain password against the stored hash and salt."""
    calculated_hash, _ = get_password_hash(plain_password, salt)
    return hmac.compare_digest(calculated_hash.encode('utf-8'), hashed_password.encode('utf-8'))


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def base64url_decode(data: str) -> bytes:
    # Re-add padding if needed
    rem = len(data) % 4
    if rem > 0:
        data += '=' * (4 - rem)
    return base64.urlsafe_b64decode(data.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[int] = None) -> str:
    """Create a standard HS256 signed JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = data.copy()
    
    expire = time.time() + (expires_delta or DEFAULT_EXPIRE_SECONDS)
    payload["exp"] = int(expire)
    
    # Encode header and payload
    header_b64 = base64url_encode(json.dumps(header).encode('utf-8'))
    payload_b64 = base64url_encode(json.dumps(payload).encode('utf-8'))
    
    # Create signature
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify an HS256 signed JWT token.
    
    Raises HTTPException for expired or invalid signatures.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token segments")
            
        header_b64, payload_b64, signature_b64 = parts
        
        # Verify Signature
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        expected_signature_b64 = base64url_encode(expected_signature)
        
        # Constant time comparison to prevent timing attacks
        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            raise ValueError("Signature mismatch")
            
        # Parse payload
        payload = json.loads(base64url_decode(payload_b64).decode('utf-8'))
        
        # Check Expiry
        if "exp" in payload and payload["exp"] < time.time():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# FastAPI Dependency injections for endpoint guards
def get_current_user_payload(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    return decode_access_token(token)

def get_auth_user(payload: Dict[str, Any] = Depends(get_current_user_payload)):
    return payload

def require_role(allowed_roles: list):
    def dependency(payload: Dict[str, Any] = Depends(get_current_user_payload)) -> Dict[str, Any]:
        user_role = payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted under user scope"
            )
        return payload
    return dependency
