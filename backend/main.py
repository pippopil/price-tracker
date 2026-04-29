from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models import SessionLocal, TrackedProduct
from scheduler import start_scheduler

app = FastAPI(title="Price Tracker API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class TrackRequest(BaseModel):
    url: str
    user_id: int  # В реальном проекте берётся из авторизации

@app.on_event("startup")
def startup():
    start_scheduler()

@app.post("/track/")
def track_product(req: TrackRequest, db: Session = Depends(get_db)):
    mp = ""
    if "ozon.ru" in req.url: mp = "ozon"
    elif "wildberries.ru" in req.url: mp = "wildberries"
    elif "market.yandex" in req.url: mp = "yandex"
    elif "aliexpress" in req.url: mp = "aliexpress"
    else:
        raise HTTPException(400, "Неподдерживаемый маркетплейс")

    from scraper import extract_product_key
    key = extract_product_key(req.url, "")
    prod = TrackedProduct(user_id=req.user_id, product_key=key, url=req.url, marketplace=mp)
    db.add(prod)
    db.commit()
    return {"status": "added", "product_key": key, "marketplace": mp}

@app.get("/products/{user_id}")
def get_products(user_id: int, db: Session = Depends(get_db)):
    return db.query(TrackedProduct).filter(TrackedProduct.user_id == user_id, TrackedProduct.is_active == True).all()

@app.post("/stop/{track_id}")
def stop_tracking(track_id: int, db: Session = Depends(get_db)):
    prod = db.query(TrackedProduct).get(track_id)
    if not prod:
        raise HTTPException(404, "Не найдено")
    prod.is_active = False
    db.commit()
    return {"status": "stopped"}