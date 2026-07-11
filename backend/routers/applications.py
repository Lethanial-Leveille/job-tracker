from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from services.application import create_application,get_application, list_applications, update_application, delete_application
from database import get_db
from schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate

router = APIRouter(prefix="/applications", tags=["applications"])

@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create(data: ApplicationCreate, db: Session = Depends(get_db)) -> ApplicationRead:
    new_application = create_application(db, data)
    return new_application

@router.get("/{application_id}", response_model=ApplicationRead)
def read_one(application_id: str, db: Session = Depends(get_db)) -> ApplicationRead:
    result = get_application(db, application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found") 
    return result

@router.get("", response_model=list[ApplicationRead])
def list_all(db: Session = Depends(get_db)) -> list[ApplicationRead]:
    return list_applications(db)

@router.patch("/{application_id}", response_model=ApplicationRead)
def update(application_id: str, data: ApplicationUpdate, db: Session = Depends(get_db)) -> ApplicationRead:
    result = update_application(db, data, application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found") 
    return result

@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(application_id: str, db: Session = Depends(get_db)) -> None:
    result = delete_application(db, application_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return None




    
