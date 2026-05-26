import { useEffect, useState } from 'react';
import api from '../api/client';

/**
 * 전체 환자 수를 조회 (empty-state 게이팅용).
 * count === 0 → CSV 업로드 전 상태
 * loading === true → 아직 조회 중 (pages should show spinner)
 */
export default function usePatientCount() {
  const [count, setCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get('/patients/count')
      .then((res) => {
        if (cancelled) return;
        setCount(res.data?.data?.count ?? 0);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err);
        setCount(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { count, loading, error };
}
