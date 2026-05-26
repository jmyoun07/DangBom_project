"""
ML 예측 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Patient
from models.schemas import PredictRequest, SimulateRequest
from ml.predictor import predict_all, predict_with_simulation

router = APIRouter(prefix="/api/v1", tags=["prediction"])


def _patient_to_dict(p: Patient) -> dict:
    """ORM Patient -> dict."""
    return {c.name: getattr(p, c.name) for c in p.__table__.columns}


@router.post("/predict")
def predict(body: PredictRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    result = predict_all(_patient_to_dict(patient))
    return {"data": result, "success": True}


@router.post("/predict/simulate")
def simulate(body: SimulateRequest, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    result = predict_with_simulation(
        _patient_to_dict(patient), body.c_peptide, body.hba1c
    )
    return {"data": result, "success": True}
