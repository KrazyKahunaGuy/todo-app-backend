from typing import Any, Optional, Union

import cloudinary.uploader
from cloudinary.exceptions import Error
from fastapi import APIRouter, Depends, HTTPException, Query, Security, status, File
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from todo.api_v1.config import Config
from todo.api_v1.schemas.user_schema import (
    AccessTokenData, UserCreate, User, Credentials, TokenData, UserProfile)
from todo.api_v1.schemas.error_response_schema import ErrorResponse, error_responses
from todo.api_v1.dependencies.database import get_db
from todo.api_v1.database.actions.user_actions import (
    create_user, get_user_by_id, get_user_by_username, set_profile_image, authentication_handler)

router = APIRouter(prefix=Config.API_VERSION_STRING, tags=['User'])
security = HTTPBearer(scheme_name='Bearer')
cloudinary.config(cloud_name=Config.CLOUDINARY_CLOUD_NAME,
                  api_key=Config.CLOUDINARY_CLOUD_API_KEY,
                  api_secret=Config.CLOUDINARY_CLOUD_API_SECRET)


@router.post('/users', tags=['User'], responses=error_responses)
def create_user_route(user: UserCreate,
                      db: Session = Depends(get_db)):
    """
    API route to create a new user instance
    """
    try:
        create_user(db=db, user=user)
        return {'message': 'User created successfully'}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=jsonable_encoder(ErrorResponse(
            message='Internal server error', code=status.HTTP_500_INTERNAL_SERVER_ERROR)))


@router.post("/users/login", tags=["User"], response_model=Union[TokenData, dict], responses=error_responses)
def login_user(credentials: Credentials, db: Session = Depends(get_db)):
    """
    API route to login a user
    """
    try:
        user = get_user_by_username(db=db, username=credentials.username)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=jsonable_encoder(ErrorResponse(
                message="Username not found", code=status.HTTP_401_UNAUTHORIZED)))

        if not authentication_handler.decode_password(credentials.password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=jsonable_encoder(ErrorResponse(
                message="Invalid password", code=status.HTTP_401_UNAUTHORIZED)))
        access_token = authentication_handler.encode_jwt_token(
            username=user.username)
        refresh_token = authentication_handler.encode_jwt_refresh_token(
            username=user.username)
        return {"access_token": access_token, "refresh_token": refresh_token}
    except Exception as e:
        raise e


@router.get('/users/me', response_model=Union[UserProfile, dict], tags=['User'], responses=error_responses)
def get_user_profile(credentials: HTTPAuthorizationCredentials = Security(security),
                     db: Session = Depends(get_db)):
    """
    API route to get a user profile
    """
    access_token = credentials.credentials
    username = authentication_handler.decode_jwt_token(access_token)
    try:
        user = get_user_by_username(db=db, username=username)
        return {"username": user.username, "profile_image": user.profile_image}
    except Exception as e:
        raise e


@router.post('/users/me/upload', tags=['User'], responses=error_responses)
def upload_profile_image(profile_image: bytes = File(...), credentials: HTTPAuthorizationCredentials = Security(security), db: Session = Depends(get_db)):
    """
    API route to upload a profile image
    """
    access_token = credentials.credentials
    username = authentication_handler.decode_jwt_token(access_token)
    try:
        user = get_user_by_username(db=db, username=username)
        if user:
            if profile_image is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=jsonable_encoder(
                    ErrorResponse(code=status.HTTP_400_BAD_REQUEST, message="No file uploaded")))
            profile_image = cloudinary.uploader.upload(profile_image, allowed_formats=[
                'png', 'jpg', 'jpeg'], public_id=user.username)
            profile_image_url = profile_image["secure_url"]
            print(profile_image_url)
            set_profile_image(db=db, user=user,
                              image_url=profile_image_url)
            return {"message": "Profile image uploaded successfully",
                    "url": profile_image_url}
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=jsonable_encoder(
            ErrorResponse(code=status.HTTP_404_NOT_FOUND, message="User not found")))
    except Exception as e:
        if isinstance(e, Error):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=jsonable_encoder(
                ErrorResponse(code=status.HTTP_400_BAD_REQUEST, message=e.args[0])))
        raise e


@ router.get("/users/refresh", tags=["User"], response_model=Union[AccessTokenData, Any], responses=error_responses)
def refresh_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        refresh_token = credentials.credentials
        new_jwt_token = authentication_handler.refresh_jwt_token(refresh_token)
        return {"access_token": new_jwt_token}
    except Exception as e:
        raise e


@ router.get('/users', response_model=User, tags=['User'])
def get_user_route(user_id: Optional[int] = Query(None, alias="id"),
                   username: Optional[str] = Query(
                       None, alias="username", max_length=10),
                   db: Session = Depends(get_db)):
    """
    API route to get a user instance by id or by username
    """
    try:
        if user_id:
            return get_user_by_id(db=db, user_id=user_id)
        if username:
            return get_user_by_username(db=db, username=username)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=jsonable_encoder(ErrorResponse(
            message="User not found", code=status.HTTP_404_NOT_FOUND)))
