from fastapi import FastAPI

app = FastAPI(title= "Job Tracker")

applications = {}

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/applications")
def show_applications():
    return applications

@app.post("/applications")
def add_applications(status=str,type=str,priority=str,deadline=str):
    applications[status] = "hello"
    return "Application Posted!" 

@app.get("/applications/{application_id}")
def get_application(application_id: int):
    application = applications[application_id]
    return application
