from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import SessionLocal, TrackedProduct
from scheduler import start_scheduler
from scraper import extract_product_key

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class TrackReq(BaseModel):
    url: str
    user_id: int

@app.on_event("startup")
def startup():
    start_scheduler()

@app.post("/track/")
def track(req: TrackReq, db: Session = Depends(get_db)):
    mp = ""
    if "ozon.ru" in req.url: mp = "ozon"
    elif "wildberries.ru" in req.url: mp = "wildberries"
    elif "market.yandex" in req.url: mp = "yandex"
    elif "aliexpress" in req.url: mp = "aliexpress"
    else: raise HTTPException(400, "Неподдерживаемый маркетплейс")

    db.add(TrackedProduct(user_id=req.user_id, product_key=extract_product_key(req.url), url=req.url, marketplace=mp))
    db.commit()
    return {"status": "ok", "mp": mp}

@app.get("/products/{uid}")
def get_prods(uid: int, db: Session = Depends(get_db)):
    return db.query(TrackedProduct).filter(TrackedProduct.user_id == uid, TrackedProduct.is_active).all()

@app.post("/stop/{tid}")
def stop(tid: int, db: Session = Depends(get_db)):
    prod = db.query(TrackedProduct).get(tid)
    if not prod: raise HTTPException(404, "Не найдено")
    prod.is_active = False
    db.commit()
    return {"status": "stopped"}