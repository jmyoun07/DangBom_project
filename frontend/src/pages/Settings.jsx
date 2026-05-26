import { useState } from 'react';
import { Save, Trash2, Download as DownloadIcon, Palette, Database, AlertTriangle, CheckCircle, Sparkles, ShieldCheck, HardDriveDownload, Activity } from 'lucide-react';
import api from '../api/client';
import usePatientCount from '../hooks/usePatientCount';
import { useTheme } from '../contexts/ThemeContext';
import { useToast } from '../contexts/ToastContext';
import { useConfirm } from '../contexts/ConfirmContext';
import DiagnosticsPanel from '../components/DiagnosticsPanel';

const ACCENT_COLORS = [
  { value: '#6366f1', name: '\uC778\uB514\uACE0', sub: 'Default' },
  { value: '#0ea5e9', name: '\uBE14\uB8E8', sub: 'Sky' },
  { value: '#10b981', name: '\uC5D0\uBA54\uB784\uB4DC', sub: 'Emerald' },
  { value: '#f59e0b', name: '\uC624\uB80C\uC9C0', sub: 'Amber' },
  { value: '#ef4444', name: '\uB808\uB4DC', sub: 'Red' },
  { value: '#8b5cf6', name: '\uBC14\uC774\uC62C\uB81B', sub: 'Violet' },
];

export default function Settings() {
  const { count } = usePatientCount();
  const { settings, setSettings, saveSettings, resetSettings } = useTheme();
  const toast = useToast();
  const confirm = useConfirm();
  const [clearing, setClearing] = useState(false);
  const [backingUp, setBackingUp] = useState(false);

  const update = (key, value) => {
    setSettings((prev) => {
      const next = { ...prev, [key]: value };
      if (key === 'accentColor' || key === 'density') {
        try { localStorage.setItem('dbcare.settings.v1', JSON.stringify(next)); } catch (e) { /* noop */ }
      }
      return next;
    });
  };

  const save = () => {
    saveSettings();
    toast.success('\uC124\uC815\uC774 \uC800\uC7A5\uB418\uC5C8\uC2B5\uB2C8\uB2E4.');
  };

  const reset = async () => {
    const ok = await confirm({
      title: '\uC124\uC815 \uCD08\uAE30\uD654',
      message: '\uD14C\uB9C8 \uBC0F \uD45C\uC2DC \uC124\uC815\uC744 \uAE30\uBCF8\uAC12\uC73C\uB85C \uB418\uB3CC\uB9B4\uAE4C\uC694?',
      confirmLabel: '\uCD08\uAE30\uD654',
      cancelLabel: '\uCDE8\uC18C',
    });
    if (!ok) return;
    resetSettings();
    toast.info('\uC124\uC815\uC774 \uAE30\uBCF8\uAC12\uC73C\uB85C \uCD08\uAE30\uD654\uB418\uC5C8\uC2B5\uB2C8\uB2E4.');
  };

  const backupPatients = async () => {
    if ((count ?? 0) === 0) {
      toast.info('\uBC31\uC5C5\uD560 \uD658\uC790 \uB370\uC774\uD130\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.');
      return;
    }
    setBackingUp(true);
    try {
      const res = await api.get('/patients/backup', { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const today = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '').slice(0, 15);
      a.href = url;
      a.download = `dbcare_patients_backup_${today}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success(`${count}\uBA85\uC758 \uD658\uC790 \uB370\uC774\uD130\uAC00 CSV\uB85C \uC800\uC7A5\uB418\uC5C8\uC2B5\uB2C8\uB2E4.`, { title: '\uBC31\uC5C5 \uC644\uB8CC' });
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message, { title: '\uBC31\uC5C5 \uC2E4\uD328' });
    } finally {
      setBackingUp(false);
    }
  };

  const clearAllPatients = async () => {
    const ok = await confirm({
      title: `\uC804\uCCB4 \uD658\uC790 \uB370\uC774\uD130 \uC0AD\uC81C (${count}\uBA85)`,
      message: '\u26A0\uFE0F \uC774 \uC791\uC5C5\uC740 \uB418\uB3CC\uB9B4 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.\n\uBC31\uC5C5\uC744 \uBA3C\uC800 \uC800\uC7A5\uD588\uB294\uC9C0 \uD655\uC778\uD558\uC138\uC694.\n\n\uC9C4\uD589\uD558\uB824\uBA74 \uD655\uC778\uB780\uC5D0 DELETE \uB97C \uC785\uB825\uD558\uC138\uC694.',
      tone: 'danger',
      requireText: 'DELETE',
      confirmLabel: '\uC601\uAD6C \uC0AD\uC81C',
      cancelLabel: '\uCDE8\uC18C',
    });
    if (!ok) return;
    setClearing(true);
    try {
      const res = await api.delete('/patients');
      const deleted = res.data?.data?.deleted_count || 0;
      toast.success(`${deleted}\uBA85\uC758 \uD658\uC790 \uB370\uC774\uD130\uAC00 \uC0AD\uC81C\uB418\uC5C8\uC2B5\uB2C8\uB2E4.`, { title: '\uC0AD\uC81C \uC644\uB8CC' });
      try { localStorage.removeItem('dbcare.recentPatients.v1'); } catch {}
      setTimeout(() => window.location.reload(), 1200);
    } catch (e) {
      toast.error(e.response?.data?.detail || e.message, { title: '\uC0AD\uC81C \uC2E4\uD328' });
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="w-full fade-in">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900 tracking-tight">{'\uC124\uC815'}</h1>
        <p className="text-sm text-gray-500 mt-1">{'\uD14C\uB9C8 \uBC0F \uD658\uC790 \uB370\uC774\uD130 \uAD00\uB9AC'}</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* 테마 */}
        <section className="card-elevated p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Palette size={18} className="text-accent" />
              <h2 className="text-base font-bold text-gray-900">{'\uD14C\uB9C8 \uBC0F \uD45C\uC2DC'}</h2>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] text-gray-500 bg-gray-50 border border-gray-200 px-2 py-1 rounded-full">
              <Sparkles size={11} className="text-accent" />
              {'\uD074\uB9AD \uC989\uC2DC \uC801\uC6A9'}
            </span>
          </div>

          <div className="space-y-5">
            <div>
              <span className="text-xs font-medium text-gray-600 mb-2 block">{'\uC0C9\uC0C1 \uD14C\uB9C8'}</span>
              <div className="grid grid-cols-3 gap-2">
                {ACCENT_COLORS.map((c) => {
                  const selected = settings.accentColor === c.value;
                  return (
                    <button
                      key={c.value}
                      onClick={() => update('accentColor', c.value)}
                      className={`flex items-center gap-2.5 p-2.5 rounded-xl border-2 transition-all text-left ${
                        selected
                          ? 'border-gray-900 shadow-sm bg-gray-50/50'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/50'
                      }`}
                    >
                      <span className="w-6 h-6 rounded-lg shadow-sm shrink-0" style={{ backgroundColor: c.value }} />
                      <span className="flex flex-col leading-tight">
                        <span className="text-xs font-semibold text-gray-800">{c.name}</span>
                        <span className="text-[10px] text-gray-400">{c.sub}</span>
                      </span>
                      {selected && <CheckCircle size={14} className="ml-auto text-gray-900" />}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <span className="text-xs font-medium text-gray-600 mb-2 block">{'\uD654\uBA74 \uBC00\uB3C4'}</span>
              <div className="flex gap-2">
                {[
                  { v: 'comfortable', l: '\uB113\uAC8C (\uAE30\uBCF8)' },
                  { v: 'compact', l: '\uC881\uAC8C' },
                ].map((opt) => (
                  <button
                    key={opt.v}
                    onClick={() => update('density', opt.v)}
                    className={`px-4 py-2 rounded-lg text-xs font-medium border transition-colors ${
                      settings.density === opt.v
                        ? 'bg-accent text-white border-transparent'
                        : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {opt.l}
                  </button>
                ))}
              </div>
            </div>

            <label className="flex items-center gap-3 cursor-pointer pt-1">
              <input
                type="checkbox"
                checked={settings.showEnglishLabels}
                onChange={(e) => update('showEnglishLabels', e.target.checked)}
                className="w-4 h-4"
                style={{ accentColor: 'var(--db-accent)' }}
              />
              <span className="text-xs text-gray-700">{'\uC601\uBB38 \uD569\uBCD1\uC99D\uBA85 \uD568\uAED8 \uD45C\uC2DC (Dashboard)'}</span>
            </label>
          </div>
        </section>

        {/* 데이터 관리 */}
        <section className="card-elevated p-5">
          <div className="flex items-center gap-2 mb-4">
            <Database size={18} className="text-accent" />
            <h2 className="text-base font-bold text-gray-900">{'\uB370\uC774\uD130 \uAD00\uB9AC'}</h2>
          </div>

          {/* 등록 환자 수 */}
          <div className="bg-gray-50 rounded-xl p-3.5 text-center border border-gray-100 mb-4">
            <p className="text-[11px] text-gray-500 mb-0.5">{'\uD604\uC7AC \uB4F1\uB85D\uB41C \uD658\uC790'}</p>
            <p className="text-2xl font-bold text-gray-900">
              {count ?? '\u2014'}
              <span className="text-sm font-semibold text-gray-500 ml-0.5">{'\uBA85'}</span>
            </p>
          </div>

          {/* 백업 */}
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-4 mb-4">
            <div className="flex items-start gap-2 mb-2.5">
              <ShieldCheck size={16} className="text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <p className="text-xs font-bold text-emerald-700 mb-0.5">
                  {'\uD658\uC790 \uB370\uC774\uD130 \uBC31\uC5C5'}
                </p>
                <p className="text-[11px] text-emerald-700/80 leading-relaxed">
                  {'\uC804\uCCB4 \uD658\uC790 \uB370\uC774\uD130\uB97C CSV \uD30C\uC77C\uB85C \uC800\uC7A5\uD569\uB2C8\uB2E4. \uC0AD\uC81C \uC804\uC5D0 \uBC18\uB4DC\uC2DC \uBC31\uC5C5\uC744 \uC800\uC7A5\uD558\uC138\uC694.'}
                </p>
              </div>
            </div>
            <button
              onClick={backupPatients}
              disabled={backingUp || (count ?? 0) === 0}
              className="flex items-center gap-2 px-4 py-2 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-semibold hover:bg-emerald-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <HardDriveDownload size={14} />
              {backingUp ? '\uBC31\uC5C5 \uC911...' : '\uC804\uCCB4 \uD658\uC790 \uB370\uC774\uD130 \uBC31\uC5C5 (CSV)'}
            </button>
          </div>

          {/* CSV 템플릿 */}
          <a
            href="http://localhost:8000/api/v1/upload/template"
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-50 transition-colors mb-4 w-fit"
          >
            <DownloadIcon size={14} />
            {'CSV \uC5C5\uB85C\uB4DC \uD15C\uD50C\uB9BF \uB2E4\uC6B4\uB85C\uB4DC'}
          </a>

          {/* 위험 구역 */}
          <div className="border-t border-red-100 pt-4">
            <p className="text-xs font-bold text-red-600 mb-1 flex items-center gap-1">
              <AlertTriangle size={12} /> {'\uC704\uD5D8 \uAD6C\uC5ED'}
            </p>
            <p className="text-xs text-gray-500 mb-3 leading-relaxed">
              {'\uBAA8\uB4E0 \uD658\uC790 \uB370\uC774\uD130\uB97C \uC644\uC804 \uC0AD\uC81C\uD569\uB2C8\uB2E4. '}
              <span className="text-red-600 font-semibold">{'\uBC18\uB4DC\uC2DC \uBC31\uC5C5 \uB2E4\uC6B4\uB85C\uB4DC \uD6C4 \uC2E4\uD589\uD558\uC138\uC694.'}</span>
            </p>
            <button
              onClick={clearAllPatients}
              disabled={clearing || (count ?? 0) === 0}
              className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 size={14} />
              {clearing ? '\uC0AD\uC81C \uC911...' : '\uC804\uCCB4 \uD658\uC790 \uB370\uC774\uD130 \uC0AD\uC81C'}
            </button>
          </div>
        </section>
      </div>

      {/* Save & Reset */}
      <div className="flex items-center justify-end gap-2 pt-5">
        <button
          onClick={reset}
          className="px-4 py-2 text-xs font-semibold text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {'\uAE30\uBCF8\uAC12\uC73C\uB85C \uB418\uB3CC\uB9AC\uAE30'}
        </button>
        <button
          onClick={save}
          className="flex items-center gap-2 px-5 py-2.5 bg-accent hover:bg-accent-dark text-white text-xs font-semibold rounded-lg transition-colors shadow-sm"
        >
          <Save size={14} />
          {'\uC124\uC815 \uC800\uC7A5'}
        </button>
      </div>

      {/* \uD658\uACBD \uC810\uAC80 + \uB370\uC774\uD130 \uD3F4\uB354 (CSV \uBBF8\uB7EC) \u2014 v2.1.1 \uCD94\uAC00 */}
      <section className="card-elevated p-5 mt-5">
        <div className="flex items-center gap-2 mb-4">
          <Activity size={18} className="text-accent" />
          <h2 className="text-base font-bold text-gray-900">{'\uD658\uACBD \uC810\uAC80 \uBC0F \uB370\uC774\uD130 \uD3F4\uB354'}</h2>
        </div>
        <DiagnosticsPanel />
      </section>

      <div className="text-center text-[11px] text-gray-400 pt-2">
        DB-care v2.1.6 · Diabetes Complication Predictor · {'\uBCD1\uC6D0 \uB0B4\uBD80\uC6A9'}
      </div>
    </div>
  );
}
