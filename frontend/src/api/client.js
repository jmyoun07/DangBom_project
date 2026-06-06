import axios from 'axios';

// 개발 모드 (npm run dev, 5173 포트): 별도 백엔드(VITE_API_PORT 또는 8000)에 CORS 요청
// 프로덕션/데스크톱 모드 (Tauri / PyInstaller): 동일 오리진 상대경로
const DEV_PORT = import.meta.env.VITE_API_PORT || '8000';
const baseURL = import.meta.env.DEV
  ? `http://127.0.0.1:${DEV_PORT}/api/v1`
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

export default api;
