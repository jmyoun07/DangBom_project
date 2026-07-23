import { useEffect, useState, useCallback } from 'react';
import api from '../api/client';

/**
 * 전체 환자 수를 조회 (empty-state 게이팅용).
 * count === 0 → CSV 업로드 전 상태
 * loading === true → 아직 조회 중 (pages should show spinner)
 * refetch() → 환자 추가/삭제 후 카운트 재조회 (삭제해도 카운트가 남던 문제 해소)
 */
export default function usePatientCount() {
  const [count, setCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
        // v2.2.9 (#7): 서버 장애를 count=0(='환자 없음')으로 오인하지 않도록 null 유지.
        //   게이트 페이지는 count===0 일 때만 빈 상태를, error 일 때는 연결 오류를 표시한다.
        setCount(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { count, loading, error, refetch };
}
