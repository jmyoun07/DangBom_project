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
  const token = (typeof window !== 'undefined' && window.__DBCARE_TOKEN__)
    || import.meta.env.VITE_DBCARE_API_TOKEN;
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
