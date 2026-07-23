import axios from 'axios';

// 개발 모드 (npm run dev, 5173 포트): 별도 백엔드(VITE_API_PORT 또는 8000)에 CORS 요청
// 프로덕션/데스크톱 모드 (Tauri / PyInstaller): 동일 오리진 상대경로
const DEV_PORT = import.meta.env.VITE_API_PORT || '8000';

// /health 등 /api/v1 prefix 밖의 엔드포인트용 서버 루트.
//   dev: http://127.0.0.1:PORT (baseURL 과 동일한 호스트/포트 규칙), prod: 동일 오리진 상대경로.
export const API_SERVER_ROOT = import.meta.env.DEV ? `http://127.0.0.1:${DEV_PORT}` : '';

const baseURL = import.meta.env.DEV
  ? `${API_SERVER_ROOT}/api/v1`
  : '/api/v1';

const api = axios.create({
  baseURL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  // 파일 업로드(FormData)는 Content-Type 을 지워 axios/브라우저가 multipart boundary 를 자동 설정하게 한다.
  //   인스턴스 기본값 'application/json' 이 남으면 axios transformRequest 가 FormData 를
  //   JSON({"file":{}}) 으로 직렬화해버려 서버가 file 필드를 못 받고 422 "Field required" 가 난다.
  //   (CSV/엑셀 업로드가 안 되던 근본 원인. node 재현으로 검증함.)
  if (typeof FormData !== 'undefined' && config.data instanceof FormData && config.headers) {
    if (typeof config.headers.delete === 'function') {
      config.headers.delete('Content-Type');           // AxiosHeaders 정규화 키까지 제거
    } else {
      delete config.headers['Content-Type'];
      delete config.headers['content-type'];
      if (config.headers.common) {
        delete config.headers.common['Content-Type'];
        delete config.headers.common['content-type'];
      }
    }
  }
  const token = (typeof window !== 'undefined' && window.__DBCARE_TOKEN__)
    || import.meta.env.VITE_DBCARE_API_TOKEN;
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── 에러 메시지 정규화 (단일 소스) ────────────────────────────
// 백엔드 에러 응답 규격: { error: string, detail: string | object[], success: false }
//   - `error` 는 항상 사람이 읽을 수 있는 문자열 → 최우선 사용.
//   - `detail` 은 422(입력검증)에서 FastAPI 객체 배열([{loc, msg, type}, ...]) 이다.
//     이걸 JSX 에 그대로 넣으면 React 가 "Objects are not valid as a React child" 로 크래시하므로
//     화면에 넣기 전 반드시 이 헬퍼로 문자열화한다.
export function errToText(value) {
  if (value == null) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return value.map(errToText).filter(Boolean).join(', ');
  }
  if (typeof value === 'object') {
    // FastAPI 422 항목: { loc: ['body', 'hba1c'], msg: '...', type: '...' }
    const msg = value.msg || value.message || value.reason;
    if (msg) {
      const loc = Array.isArray(value.loc)
        ? value.loc.filter((x) => x !== 'body' && x !== 'query').join('.')
        : '';
      return loc ? `${loc}: ${errToText(msg)}` : errToText(msg);
    }
    if (value.error) return errToText(value.error);
    if (value.detail) return errToText(value.detail);
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return String(value);
}

// axios 에러 → 화면에 바로 넣어도 안전한 문자열.
export function errorMessage(err, fallback = '알 수 없는 오류가 발생했습니다.') {
  const data = err?.response?.data;
  // 1순위: 백엔드가 보장하는 사람이 읽을 수 있는 문자열
  const errText = errToText(data?.error);
  if (errText) return errText;
  // 2순위: detail (배열/객체면 문자열로 변환)
  const detailText = errToText(data?.detail);
  if (detailText) return detailText;
  // 3순위: body 자체가 문자열이거나 axios 자체 메시지
  const bodyText = typeof data === 'string' ? data.trim() : '';
  if (bodyText) return bodyText;
  if (err?.message) return err.message;
  return fallback;
}

export default api;
