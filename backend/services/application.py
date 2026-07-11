from sqlalchemy.orm import Session
from sqlalchemy import select
from schemas.application import ApplicationCreate, ApplicationUpdate
from models.application import Application

def create_application(db: Session, data: ApplicationCreate) -> Application:
    application = Application(**data.model_dump())
    db.add(application)
    db.commit()
    db.refresh(application)

    return application

def get_application(db: Session, application_id: str) -> Application | None:
    return db.get(Application,application_id)

def list_applications(db: Session) -> list[Application]:
    stmt = select(Application).order_by(Application.created_at.desc())
    result = db.execute(stmt)
    return list(result.scalars().all())

def update_application(db: Session, data: ApplicationUpdate, application_id: str) -> Application | None:
    application = db.get(Application,application_id)
    if application is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(application,field,value)
    db.commit()
    db.refresh(application)
    return application

def delete_application(db: Session, application_id: str) -> Application | None:
    application = db.get(Application,application_id)
    if application is None:
        return None
    db.delete(application)
    db.commit()
    return application
