// 환자 컨텍스트 라우트 정규식 — Sidebar / PatientContextBar 공용 단일 소스.
// 새 환자별 라우트(예: /exam-history/:id)를 추가하면 여기 한 곳만 고치면 된다.
export const PATIENT_ROUTE_RE = /^\/(dashboard|patients|exam-history|risk-analysis|case-comparison|report)\/(\d+)/;

// pathname → { section, patientId } | null
export function extractPatientContext(pathname) {
  const m = pathname.match(PATIENT_ROUTE_RE);
  return m ? { section: m[1], patientId: m[2] } : null;
}

// pathname → patientId 문자열 | null
export function extractPatientId(pathname) {
  const m = pathname.match(PATIENT_ROUTE_RE);
  return m ? m[2] : null;
}
