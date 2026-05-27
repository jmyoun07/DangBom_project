// =============================================================
// DB-care v2.1.6 · 디자인 토큰 중앙 모듈
// -------------------------------------------------------------
// 이 파일이 UI 전반의 "single source of truth".
// 새 컴포넌트 작성 시 색/문구/단위는 반드시 여기서 import.
// 하드코딩된 hex, 중복 한글 리터럴, 매직넘버 방지용.
// =============================================================

// ── 위험도 등급 (enum) ────────────────────────────────────────
export const RISK_LEVELS = {
  HIGH: '\uACE0\uC704\uD5D8',    // 고위험
  MID:  '\uC911\uC704\uD5D8',    // 중위험
  LOW:  '\uC800\uC704\uD5D8',    // 저위험
  PENDING: '\uBD84\uC11D\uC911', // 분석중
  NOT_READY: '\uC900\ube44 \uc911', // 준비 중 (ML 미구현 모델용)
};

// 0-100 점수를 레벨 문자열로. 백엔드 _level() 과 cut-off 동일 (60/30).
export function scoreToLevel(score) {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= 60) return RISK_LEVELS.HIGH;
  if (score >= 30) return RISK_LEVELS.MID;
  return RISK_LEVELS.LOW;
}

// ── 위험도 색상 팔레트 (컴포넌트 간 일치) ──────────────────────
// mid 는 **amber** 로 통일 (yellow-100/600 대비 미달 문제 해소).
export const RISK_COLORS = {
  [RISK_LEVELS.HIGH]: {
    stroke: '#dc2626',            // red-600
    fill:   '#ef4444',            // red-500
    bgSoft: 'bg-red-50',
    textStrong: 'text-red-700',
    textSoft: 'text-red-600',
    border: 'border-red-200',
    badge: 'bg-red-50 text-red-700 border border-red-200',
    bar:   'bg-red-500',
    rgb:   'rgb(239, 68, 68)',
    rgba:  (a) => `rgba(239, 68, 68, ${a})`,
    icon:  '\u25B2', // ▲ 위험 상승 (색각 대비)
    ariaLabel: '\uACE0\uC704\uD5D8',
  },
  [RISK_LEVELS.MID]: {
    stroke: '#d97706',            // amber-600
    fill:   '#f59e0b',            // amber-500
    bgSoft: 'bg-amber-50',
    textStrong: 'text-amber-700',
    textSoft: 'text-amber-600',
    border: 'border-amber-200',
    badge: 'bg-amber-50 text-amber-700 border border-amber-200',
    bar:   'bg-amber-500',
    rgb:   'rgb(245, 158, 11)',
    rgba:  (a) => `rgba(245, 158, 11, ${a})`,
    icon:  '\u25C6', // ◆ 주의 (색각 대비)
    ariaLabel: '\uC911\uC704\uD5D8',
  },
  [RISK_LEVELS.LOW]: {
    stroke: '#16a34a',            // green-600
    fill:   '#22c55e',            // green-500
    bgSoft: 'bg-emerald-50',
    textStrong: 'text-emerald-700',
    textSoft: 'text-emerald-600',
    border: 'border-emerald-200',
    badge: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    bar:   'bg-emerald-500',
    rgb:   'rgb(34, 197, 94)',
    rgba:  (a) => `rgba(34, 197, 94, ${a})`,
    icon:  '\u25CF', // ● 안정 (색각 대비)
    ariaLabel: '\uC800\uC704\uD5D8',
  },
  [RISK_LEVELS.PENDING]: {
    stroke: '#6b7280',
    fill:   '#9ca3af',
    bgSoft: 'bg-gray-50',
    textStrong: 'text-gray-700',
    textSoft: 'text-gray-500',
    border: 'border-gray-200',
    badge: 'bg-gray-50 text-gray-500 border border-gray-200',
    bar:   'bg-gray-300',
    rgb:   'rgb(156, 163, 175)',
    rgba:  (a) => `rgba(156, 163, 175, ${a})`,
    icon:  '\u25CB', // ○ 평가 중
    ariaLabel: '\uBD84\uC11D\uC911',
  },
  [RISK_LEVELS.NOT_READY]: {
    stroke: '#9ca3af',
    fill:   '#d1d5db',
    bgSoft: 'bg-gray-50',
    textStrong: 'text-gray-600',
    textSoft: 'text-gray-400',
    border: 'border-gray-200',
    badge: 'bg-gray-50 text-gray-500 border border-gray-200 italic',
    bar:   'bg-gray-300',
    rgb:   'rgb(209, 213, 219)',
    rgba:  (a) => `rgba(209, 213, 219, ${a})`,
    icon:  '\u2026', // … 준비 중
    ariaLabel: '\uc900\ube44 \uc911',
  },
};

export function riskColorFor(level) {
  return RISK_COLORS[level] || RISK_COLORS[RISK_LEVELS.PENDING];
}

// ── UI 기본 토큰 ──────────────────────────────────────────────
export const ACCENT = {
  primary: 'var(--color-accent, #6366f1)',
  hover:   'var(--color-accent-hover, #4f46e5)',
};

// ── 합병증 한글 라벨 ─────────────────────────────────────────
export const DISEASE_LABELS = {
  kidney:   '\uC2E0\uC7A5\uC9C8\uD658',     // 신장질환
  cardio:   '\uC2EC혈\uad00',           // 심혈관
  cerebro:  '\ub1cc혈\uad00',           // 뇌혈관
  dementia: '\uce58\ub9e4',                 // 치매
  retina:   '\ub9dd\ub9c9\ubcd1\uc99d',     // 망막병증
  neuro:    '\uc2e0\uacbd\ubcd1\uc99d',     // 신경병증
};

// ML 모델이 아직 배포되지 않은 합병증 (Radar/Risk 화면에서 '준비 중' 표시)
// v2.1.7 — 신규 3개 (neuro/dementia/cerebro) 패키지 모델 연동 완료, set 비움.
// 일부 모델 (neuro AUC 0.61) 은 임상 사용 불가 수준이지만 화면 표시는 정상.
// usage_warning 필드로 prototype/screening 표시는 result 객체에 포함됨.
export const PENDING_DISEASE_KEYS = new Set();
export const AVAILABLE_DISEASE_KEYS = new Set(['kidney', 'retina', 'cardio']);

// ── 단위 표기 상수 (일관성 강제) ──────────────────────────────
export const UNITS = {
  hba1c:      '%',
  glucose:    'mg/dL',
  cpeptide:   'ng/mL',
  cholesterol:'mg/dL',
  triglyceride:'mg/dL',
  hdl:        'mg/dL',
  ldl:        'mg/dL',
  cr:         'mg/dL',
  bun:        'mg/dL',
  bp:         'mmHg',
  bmi:        'kg/m\u00B2',   // kg/m²
  ht:         'cm',
  wt:         'kg',
  wc:         'cm',
  ggt:        'U/L',
  ast:        'U/L',
  alt:        'U/L',
  egfr:       'mL/min/1.73m\u00B2',
  ualb:       'mg/L',
  acr:        'mg/g',
  age:        '\uC138',        // 세
  percent:    '%',
  // 축약 별명 (편의용)
  chol:       'mg/dL',
  tg:         'mg/dL',
};

// ── ML 모델 메타데이터 (UI 배지용) ────────────────────────────
export const MODEL_META = {
  kidney: {
    label: DISEASE_LABELS.kidney,
    version: 'v2.2-debias',
    algorithm: 'Stacking',
    auc: 0.752,
    cohort: 'KNHANES HN19\u201324',
    nFeatures: 38,
    ready: true,
  },
  retina: {
    label: DISEASE_LABELS.retina,
    version: 'v2.2',
    algorithm: 'XGBoost',
    auc: 0.843,
    cohort: 'KNHANES HN19\u201321',
    nFeatures: 42,
    ready: true,
  },
  cardio: {
    label: DISEASE_LABELS.cardio,
    version: 'v2.2-debias',
    algorithm: 'EasyEnsemble',
    auc: 0.761,
    cohort: 'KNHANES HN19\u201321+24',
    nFeatures: 38,
    ready: true,
  },
  // v2.1.7 \u2014 \uc2e0\uaddc 3\uac1c \ubaa8\ub378 (CatBoost \uae30\ubc18 \ud328\ud0a4\uc9c0, primary \ubaa8\ub378 \uc9c0\ud45c \ud45c\uc2dc)
  neuro: {
    label: DISEASE_LABELS.neuro,
    version: 'neuropathy-final-2026.05.22',
    algorithm: 'CatBoost (DPN primary)',
    auc: 0.613,
    cohort: 'KNHANES HN19\u201324',
    nFeatures: 38,
    ready: true,
    warning: 'RESEARCH PROTOTYPE',
  },
  dementia: {
    label: DISEASE_LABELS.dementia,
    version: 'dementia-final-2026.05.22',
    algorithm: 'CatBoost + Isotonic (age-band)',
    auc: 0.710,
    cohort: 'KNHANES HN19+21',
    nFeatures: 38,
    ready: true,
    warning: 'SCREENING TOOL (SCD proxy)',
  },
  cerebro: {
    label: DISEASE_LABELS.cerebro,
    version: 'cvd-final-2026.05.23',
    algorithm: 'CatBoost (CV_strict)',
    auc: 0.728,
    cohort: 'KNHANES HN19+20+21+24',
    nFeatures: 38,
    ready: true,
    warning: 'SCREENING TOOL (post-stroke proxy)',
  },
};

// ── 환자명 마스킹 유틸 (PHI 보호) ─────────────────────────────
// 공용/시연 화면에서 노출 최소화. 기본은 가운데 글자를 `*` 로.
export function maskName(name, { mode = 'middle' } = {}) {
  if (!name) return '';
  const s = String(name).trim();
  if (s.length <= 1) return s;
  if (mode === 'first') return s[0] + '*'.repeat(Math.max(1, s.length - 1));
  if (mode === 'last')  return '*'.repeat(Math.max(1, s.length - 1)) + s[s.length - 1];
  // middle (default): 첫글자 O 마지막글자
  if (s.length === 2) return s[0] + '*';
  return s[0] + '*'.repeat(s.length - 2) + s[s.length - 1];
}

// ── 정상 범위 참고치 (검사 수치 테이블의 '참고값' 열에 사용) ──
export const REFERENCE_RANGES = {
  hba1c:       '\u2264 5.6 (\uc815\uc0c1) / 5.7\u20136.4 (\uc8fc\uc758) / \u2265 6.5 (\ub2f9\ub1e8)',
  c_peptide:   '0.9 \u2013 7.1 ng/mL',
  glucose:     '70 \u2013 99 (\uacf5\ubcf5)',
  ggt:         '\u2264 50 U/L',
  alt:         '\u2264 40 U/L',
  ast:         '\u2264 40 U/L',
  cr:          '0.6 \u2013 1.2 mg/dL',
  cholesterol: '\u2264 199 (\uc815\uc0c1) / 200\u2013239 (\uc8fc\uc758) / \u2265 240 (\ub192\uc74c)',
  triglyceride:'\u2264 149',
  hdl:         '\u2265 60 (\uc815\uc0c1) / 40\u201359 (\uc8fc\uc758) / < 40 (\ub0ae\uc74c)',
  ldl:         '\u2264 129',
  sbp:         '\u2264 119 (\uc815\uc0c1) / 120\u2013139 (\uc8fc\uc758) / \u2265 140 (\ub192\uc74c)',
  dbp:         '\u2264 79 (\uc815\uc0c1) / 80\u201389 (\uc8fc\uc758) / \u2265 90 (\ub192\uc74c)',
  bmi:         '18.5 \u2013 22.9 (\uc815\uc0c1) / 23\u201324.9 (\uacfc\uccb4\uc911) / \u2265 25 (\ube44\ub9cc)',
};

// ── 로깅 (개발환경 외에는 PHI 안 찍음) ────────────────────────
const __DEV__ = import.meta.env?.DEV === true;
export const devLog = (...args) => { if (__DEV__) console.log(...args); };
export const devWarn = (...args) => { if (__DEV__) console.warn(...args); };
export const devError = (...args) => { if (__DEV__) console.error(...args); };
// 프로덕션에서는 stack 만 남기고 message 는 생략 (PHI 노출 방지)
export const prodSafeError = (label) => (err) => {
  if (__DEV__) console.error(label, err);
  else console.error(`[${label}] error (details hidden in prod)`);
};
