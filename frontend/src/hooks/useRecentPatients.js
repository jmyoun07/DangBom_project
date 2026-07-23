import { useEffect, useState, useCallback } from 'react';

const KEY = 'dbcare.recentPatients.v1';
const MAX = 5;

function read() {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function write(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* 무시 */ }
}

// External subscribers (so mutations in one page update Sidebar live)
const listeners = new Set();
function notify() { listeners.forEach((cb) => cb()); }

export function pushRecentPatient(p) {
  if (!p || !p.id) return;
  const entry = {
    id: p.id,
    name: p.name,
    chart_no: p.chart_no,
    age: p.age,
    sex: p.sex,
    visitedAt: Date.now(),
  };
  const list = read().filter((x) => x.id !== p.id);
  list.unshift(entry);
  write(list.slice(0, MAX));
  notify();
}

// 삭제된 환자를 '최근 환자' 목록에서 제거 (없는 환자로 이동하는 죽은 링크 방지)
export function removeRecentPatient(patientId) {
  if (patientId == null) return;
  const target = String(patientId);
  const list = read();
  const next = list.filter((x) => String(x.id) !== target);
  if (next.length === list.length) return;
  write(next);
  notify();
}

export function clearRecentPatients() {
  write([]);
  notify();
}

export default function useRecentPatients() {
  const [list, setList] = useState(() => read());

  const sync = useCallback(() => setList(read()), []);

  useEffect(() => {
    listeners.add(sync);
    // Cross-tab sync via storage event
    const onStorage = (e) => { if (e.key === KEY) sync(); };
    window.addEventListener('storage', onStorage);
    return () => {
      listeners.delete(sync);
      window.removeEventListener('storage', onStorage);
    };
  }, [sync]);

  return list;
}
