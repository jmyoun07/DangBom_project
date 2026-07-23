import { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, XCircle, RefreshCw, FolderOpen, FileSpreadsheet, AlertCircle, Activity, Cpu, HardDrive, Database } from 'lucide-react';
import api, { errorMessage } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { prodSafeError } from '../theme';

// 환경 진단 + 데이터 폴더 메뉴 — Settings 페이지에 임베드.
// 프로그램 사용에 필요한 요소(DB / pkl / 디스크) 가 모두 있는지 한 번에 보여줌.

function CheckRow({ ok, label, value }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-2">
        {ok ? (
          <CheckCircle2 size={14} className="text-emerald-500 shrink-0" />
        ) : (
          <XCircle size={14} className="text-red-500 shrink-0" />
        )}
        <span className="text-xs text-gray-700">{label}</span>
      </div>
      {value !== undefined && (
        <span className={`text-[11px] tabular-nums ${ok ? 'text-gray-600' : 'text-red-600 font-semibold'}`}>{value}</span>
      )}
    </div>
  );
}

export default function DiagnosticsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exportPath, setExportPath] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const toast = useToast();

  const runCheck = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/diagnostics');
      setData(res.data?.data || null);
    } catch (e) {
      prodSafeError('Diagnostics.fetch')(e);
      toast.error('환경 점검 실패: ' + errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const fetchExportPath = useCallback(async () => {
    try {
      const res = await api.get('/export/folder');
      setExportPath(res.data?.data?.path);
    } catch { /* noop */ }
  }, []);

  const openFolder = async () => {
    try {
      const res = await api.post('/export/open');
      if (res.data?.data?.opened) {
        toast.success('데이터 폴더를 열었습니다.');
      } else {
        toast.info(`데스크탑 모드가 아닙니다. 경로: ${res.data?.data?.path}`);
      }
    } catch (e) {
      toast.error('폴더 열기 실패: ' + errorMessage(e));
    }
  };

  const refreshExport = async () => {
    setRefreshing(true);
    try {
      const res = await api.post('/export/refresh');
      const n = res.data?.data?.patients ?? 0;
      toast.success(`${n}명의 환자 데이터를 CSV 로 다시 내보냈습니다.`);
    } catch (e) {
      toast.error('CSV 재생성 실패: ' + errorMessage(e));
    } finally {
      setRefreshing(false);
    }
  };

  // 첫 마운트 시 경로만 미리 fetch (점검은 사용자가 버튼 클릭 시)
  //   렌더 중 사이드이펙트(useState initializer 악용) → useEffect 로 이동
  useEffect(() => { fetchExportPath(); }, [fetchExportPath]);

  return (
    <div className="space-y-5">
      {/* ── 환경 점검 ──────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Activity size={14} className="text-accent" />
            환경 점검
          </h3>
          <button
            onClick={runCheck}
            disabled={loading}
            className="text-xs px-3 py-1.5 bg-accent text-white rounded-md font-semibold hover:bg-accent-dark disabled:opacity-50 flex items-center gap-1.5"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            {loading ? '점검 중...' : '지금 점검'}
          </button>
        </div>

        {!data && !loading && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-500 text-center">
            "지금 점검" 버튼을 눌러 프로그램에 필요한 요소가 모두 있는지 확인하세요.
          </div>
        )}

        {data && (
          <>
            {/* 종합 결과 */}
            <div className={`rounded-lg p-3 border flex items-center gap-2 mb-3 ${
              data.ready
                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                : 'bg-amber-50 border-amber-200 text-amber-700'
            }`}>
              {data.ready ? (
                <CheckCircle2 size={18} className="text-emerald-500 shrink-0" />
              ) : (
                <AlertCircle size={18} className="text-amber-500 shrink-0" />
              )}
              <p className="text-xs font-semibold">
                {data.ready
                  ? '모든 구성 요소 정상. 프로그램이 정상 작동할 수 있습니다.'
                  : '일부 구성 요소에 문제가 있습니다. 아래 항목 확인 후 IT 담당자에게 문의하세요.'}
              </p>
            </div>

            {/* 항목별 체크 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 mb-3">
              <CheckRow ok={data.checks.database_file}  label="환자 데이터베이스 파일" />
              <CheckRow ok={data.checks.export_folder}  label="CSV 미러 폴더" />
              <CheckRow ok={data.checks.ml_retinopathy} label="망막병증 ML 모델" />
              <CheckRow ok={data.checks.ml_kidney}      label="신장질환 ML 모델" />
              <CheckRow ok={data.checks.ml_cardio}      label="심혈관 ML 모델" />
            </div>

            {/* 상세 */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-[11px]">
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-gray-500 mb-1 flex items-center gap-1">
                  <Database size={11} /> 저장소
                </p>
                <p className="text-gray-700 break-all">DB: {data.storage.database_size_mb} MB</p>
                <p className="text-gray-700">디스크 여유: {data.storage.disk_free_gb} GB</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-gray-500 mb-1 flex items-center gap-1">
                  <Cpu size={11} /> 환경
                </p>
                <p className="text-gray-700">Python {data.environment.python_version}</p>
                <p className="text-gray-700 truncate" title={data.environment.platform}>{data.environment.platform}</p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <p className="text-gray-500 mb-1 flex items-center gap-1">
                  <HardDrive size={11} /> 데이터
                </p>
                <p className="text-gray-700">환자 {data.data_counts.patients} 명</p>
                <p className="text-gray-700">측정 기록 {data.data_counts.measurements} 건</p>
              </div>
            </div>
          </>
        )}
      </div>

      <hr className="border-gray-200" />

      {/* ── 데이터 폴더 (CSV 미러) ─────────────────── */}
      <div>
        <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2 mb-2">
          <FileSpreadsheet size={14} className="text-accent" />
          환자 데이터 폴더 (CSV)
        </h3>
        <p className="text-[11px] text-gray-500 mb-3">
          환자 정보가 변경될 때마다 Excel 로 열 수 있는 CSV 파일이 자동으로 생성됩니다.
          연도 → 월별 폴더 + 환자별 폴더로 정리되어 있어 백업·이전이 간편합니다.
        </p>

        {exportPath && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-2.5 mb-3">
            <p className="text-[10px] text-gray-500 mb-0.5">폴더 경로</p>
            <p className="text-[11px] font-mono text-gray-700 break-all">{exportPath}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            onClick={openFolder}
            className="text-xs px-3 py-2 bg-accent text-white rounded-md font-semibold hover:bg-accent-dark flex items-center gap-1.5"
          >
            <FolderOpen size={12} />
            폴더 열기
          </button>
          <button
            onClick={refreshExport}
            disabled={refreshing}
            className="text-xs px-3 py-2 bg-white border border-gray-300 text-gray-700 rounded-md font-semibold hover:bg-gray-50 disabled:opacity-50 flex items-center gap-1.5"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? '재생성 중...' : '전체 다시 내보내기'}
          </button>
        </div>
      </div>
    </div>
  );
}
