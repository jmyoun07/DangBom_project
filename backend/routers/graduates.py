"""졸업자 데이터 업로드/조회 (유사사례 분석 소스).

Settings 에서 '전지점 졸업자 통계.xlsx' 를 업로드하면 Graduate 테이블을 통째로 교체한다.
엑셀이 계속 업데이트되므로, 재배포 없이 최신 졸업자 데이터를 반영할 수 있다.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db, Graduate
from services.graduates import parse_graduates_any, load_into_db

router = APIRouter(prefix="/api/v1", tags=["graduates"])


@router.get("/graduates/count")
def graduates_count(db: Session = Depends(get_db)):
    n = db.query(Graduate).count()
    return {"data": {"count": n}, "success": True}


@router.post("/graduates/upload")
async def graduates_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # v2.3.0 (감사): /upload/csv 와 동일 수준의 서버측 검증 — 크기 상한 + 매직바이트.
    #   이전엔 검증 없이 pd.ExcelFile 로 직행해 대용량/비엑셀 파일에 취약했다.
    content = await file.read()
    MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB).",
        )
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    looks_zip = content[:2] == b"PK"                  # xlsx/xlsm (zip)
    looks_ole = content[:4] == b"\xD0\xCF\x11\xE0"    # 구형 .xls (OLE2)
    # 병원이 주는 raw 졸업자 데이터셋은 csv(long 포맷)로도 온다 → csv 허용.
    #   바이너리 시그니처가 아니면 텍스트로 디코딩되는지로 판별한다.
    looks_csv = False
    if not (looks_zip or looks_ole):
        for enc in ("utf-8-sig", "cp949"):
            try:
                head = content[:4096].decode(enc)
                if "," in head or "\t" in head:
                    looks_csv = True
                    break
            except UnicodeDecodeError:
                continue
    if not (looks_zip or looks_ole or looks_csv):
        raise HTTPException(
            status_code=400,
            detail="엑셀(.xlsx/.xls) 또는 CSV 파일만 업로드 가능합니다. 파일 형식을 확인해 주세요.",
        )
    try:
        rows = parse_graduates_any(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"파일 파싱 실패: {e}")
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="유효한 졸업자 행이 없습니다. (long 포맷: visit_type 초진/졸업 2행 + hba1c, "
                   "또는 wide 포맷: 치료전/치료후 HbA1c)",
        )
    try:
        n = load_into_db(db, rows)
    except Exception as e:
        db.rollback()  # 실패 시 롤백 — 기존 졸업자 데이터 보존
        raise HTTPException(status_code=500, detail=f"졸업자 데이터 저장 실패(기존 데이터 보존됨): {e}")
    return {"data": {"loaded": n, "file_name": file.filename}, "success": True}
