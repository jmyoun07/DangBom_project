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
  INSUFFICIENT: '데이터부족', // v2.2.8 병원정책 — 필수검사 누락(추정 안 함)
};

// 0-100 점수를 레벨 문자열로 — FALLBACK 전용.
// v2.1.9 (감사 — 등급 통일): 등급의 단일 진실 소스는 backend 의 모델 threshold 기반
// _classify_risk 다. 모든 화면은 API 응답의 `level` 을 우선 사용하고, level 이
// 없을 때(legacy/오류)만 이 30/60 고정 fallback 을 쓴다. (RadarChart/RiskBar/Dashboard 모두 `level || scoreToLevel` 패턴)
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
  [RISK_LEVELS.INSUFFICIENT]: {
    stroke: '#78716c',
    fill:   '#a8a29e',
    bgSoft: 'bg-gray-50',
    textStrong: 'text-gray-700',
    textSoft: 'text-gray-500',
    border: 'border-gray-300',
    badge: 'bg-gray-100 text-gray-600 border border-gray-300',
    bar:   'bg-gray-300',
    rgb:   'rgb(168, 162, 158)',
    rgba:  (a) => `rgba(168, 162, 158, ${a})`,
    icon:  '\u26A0', // ⚠ 데이터 부족
    ariaLabel: '데이터부족',
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
  neuro:    '\uB9D0\uCD08\uC2E0\uACBD\uBCD1\uC99D', // 말초신경병증
  retina:   '\ub9dd\ub9c9\ubcd1\uc99d',     // 망막병증
  kidney:   '\uC2E0\uC7A5\uC9C8\uD658',     // 신장질환
  cardio:   '\uC2EC혈\uad00',           // 심혈관
  cerebro:  '\ub1cc혈\uad00',           // 뇌혈관
  dementia: '\uce58\ub9e4',                 // 치매
};

// ML 모델이 아직 배포되지 않은 합병증 (Radar/Risk 화면에서 '준비 중' 표시)
// v2.1.7 — 신규 3개 (neuro/dementia/cerebro) 패키지 모델 연동 완료, set 비움.
// 일부 모델 (neuro AUC 0.61) 은 임상 사용 불가 수준이지만 화면 표시는 정상.
// usage_warning 필드로 prototype/screening 표시는 result 객체에 포함됨.
export const PENDING_DISEASE_KEYS = new Set();
export const AVAILABLE_DISEASE_KEYS = new Set([
  'kidney', 'retina', 'cardio',
  'neuro', 'dementia', 'cerebro',  // v2.1.7 — 신규 3개 패키지 모델 연동 완료
]);

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
  // \uc54c\uace0\ub9ac\uc998 \ud45c\uae30: \uc784\uc0c1 \ub3c4\uad6c \uc2e0\ub8b0\uac10 \u2014 \ud559\uc220 \uc794\uc7ac/AUC \ub178\ucd9c \uc81c\uac70.
  // \ub0b4\ubd80 \ud559\uc2b5 \uba54\ud0c0\ub370\uc774\ud130(\uc608: monotone constraints, base/meta \ubd84\ub9ac, isotonic \ubcf4\uc815)\ub294
  // pkl \uc548\uc5d0 \uc720\uc9c0\ud558\uc9c0\ub9cc \ud654\uba74\uc5d0\ub294 \ub2e8\uc21c \uac00\uc871\uba85\ub9cc \ud45c\uc2dc.
  kidney: {
    label: DISEASE_LABELS.kidney,
    version: 'v2.2',
    algorithm: 'Stacking Ensemble',
    algorithmShort: 'Stacking',
    cohort: 'KNHANES HN19\u201324',
    nFeatures: 38,
    ready: true,
  },
  retina: {
    label: DISEASE_LABELS.retina,
    version: 'v2.2',
    algorithm: 'XGBoost',
    algorithmShort: 'XGBoost',
    cohort: 'KNHANES HN19\u201321',
    nFeatures: 42,
    ready: true,
  },
  cardio: {
    label: DISEASE_LABELS.cardio,
    version: 'v2.2',
    algorithm: 'Easy Ensemble',
    algorithmShort: 'Easy Ensemble',
    cohort: 'KNHANES HN19\u201321+24',
    nFeatures: 38,
    ready: true,
  },
  neuro: {
    label: DISEASE_LABELS.neuro,
    version: 'v2.2',
    algorithm: 'CatBoost',
    algorithmShort: 'CatBoost',
    cohort: 'KNHANES HN19\u201324',
    nFeatures: 38,
    ready: true,
  },
  dementia: {
    label: DISEASE_LABELS.dementia,
    version: 'v2.2',
    algorithm: 'Calibrated CatBoost',
    algorithmShort: 'CatBoost',
    cohort: 'KNHANES HN19+21',
    nFeatures: 38,
    ready: true,
  },
  cerebro: {
    label: DISEASE_LABELS.cerebro,
    version: 'v2.2',
    algorithm: 'CatBoost',
    algorithmShort: 'CatBoost',
    cohort: 'KNHANES HN19+20+21+24',
    nFeatures: 38,
    ready: true,
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

// 성별 한글 표기 — 백엔드 normalize_sex 정책(미상/결측을 임의로 여성 처리하지 않음)과 일치.
//   'M'/'F' 만 남/여로 표기하고, null·미상·레거시값('U','남성' 등)은 '미상'으로 둔다. (의료 리포트 왜곡 방지)
export const sexKo = (s) => (s === 'M' ? '남' : s === 'F' ? '여' : '미상');

// ── 정상 범위 참고치 + 판정 기준 (단일 소스) ──────────────────
// 검사 수치 테이블(PatientDetail)의 '참고값' 표시(text)와 비고 판정(evaluate)이 모두 여기서 나온다.
// 판정 라벨: '정상' | '주의' | '높음' | '낮음' | (BMI) '저체중' | '과체중' | '비만'
export const REFERENCE_RANGES = {
  hba1c: {
    text: '≤ 5.6 (정상) / 5.7–6.4 (주의) / ≥ 6.5 (당뇨)',
    evaluate: (v) => v == null ? '' : v <= 5.6 ? '정상' : v <= 6.4 ? '주의' : '높음',
  },
  c_peptide: {
    text: '1.0 – 3.5 ng/mL',
    evaluate: (v) => v == null ? '' : v < 1.0 ? '낮음' : v <= 3.5 ? '정상' : '높음',
  },
  glucose: {
    text: '70–99 (정상) / 100–125 (주의) / ≥ 126 (당뇨)',
    evaluate: (v) => v == null ? '' : v < 70 ? '낮음' : v <= 99 ? '정상' : v <= 125 ? '주의' : '높음',
  },
  ggt: {
    text: '≤ 50 U/L',
    evaluate: (v) => v == null ? '' : v <= 50 ? '정상' : '높음',
  },
  alt: {
    text: '≤ 40 U/L',
    evaluate: (v) => v == null ? '' : v <= 40 ? '정상' : '높음',
  },
  ast: {
    text: '≤ 40 U/L',
    evaluate: (v) => v == null ? '' : v <= 40 ? '정상' : '높음',
  },
  cr: {
    text: '0.6 – 1.2 mg/dL',
    evaluate: (v) => v == null ? '' : v < 0.6 ? '낮음' : v <= 1.2 ? '정상' : '높음',
  },
  cholesterol: {
    text: '≤ 199 (정상) / 200–239 (주의) / ≥ 240 (높음)',
    evaluate: (v) => v == null ? '' : v <= 199 ? '정상' : v <= 239 ? '주의' : '높음',
  },
  triglyceride: {
    text: '≤ 149 (정상) / 150–199 (주의) / ≥ 200 (높음)',
    evaluate: (v) => v == null ? '' : v <= 149 ? '정상' : v <= 199 ? '주의' : '높음',
  },
  hdl: {
    text: '≥ 60 (정상) / 40–59 (주의) / < 40 (낮음)',
    evaluate: (v) => v == null ? '' : v >= 60 ? '정상' : v >= 40 ? '주의' : '낮음',
  },
  ldl: {
    text: '≤ 129 (정상) / 130–159 (주의) / ≥ 160 (높음)',
    evaluate: (v) => v == null ? '' : v <= 129 ? '정상' : v <= 159 ? '주의' : '높음',
  },
  sbp: {
    text: '≤ 119 (정상) / 120–139 (주의) / ≥ 140 (높음)',
    evaluate: (v) => v == null ? '' : v <= 119 ? '정상' : v <= 139 ? '주의' : '높음',
  },
  dbp: {
    text: '≤ 79 (정상) / 80–89 (주의) / ≥ 90 (높음)',
    evaluate: (v) => v == null ? '' : v <= 79 ? '정상' : v <= 89 ? '주의' : '높음',
  },
  bmi: {
    text: '< 18.5 (저체중) / 18.5–22.9 (정상) / 23–24.9 (과체중) / ≥ 25 (비만)',
    evaluate: (v) => v == null ? '' : v < 18.5 ? '저체중' : v <= 22.9 ? '정상' : v <= 24.9 ? '과체중' : '비만',
  },
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
