// 합병증 카드 · 주요 위험 요인 패널 공유 로직 (Dashboard / PatientDetail 공용).
//   대시보드↔상세정보 박스 교환(병원 6/13)에 따라 양쪽에서 동일 로직을 재사용한다.
import { UNITS } from '../theme';

export const complicationCards = [
  { type: 'neuropathy',     name: '당뇨병성 말초신경병증', englishName: 'PERIPHERAL NEUROPATHY',     metricLabel: `HDL (${UNITS.chol})`, metricKey: 'hdl' },
  { type: 'retinopathy',    name: '당뇨병성 망막병증',     englishName: 'RETINOPATHY',               metricLabel: '위험 점수',           metricKey: 'score' },
  { type: 'kidney',         name: '당뇨병성 신장질환',     englishName: 'KIDNEY DISEASE',            metricLabel: `eGFR (${UNITS.egfr})`, metricKey: 'eGFR' },
  { type: 'cardiovascular', name: '당뇨병성 심혈관 질환',  englishName: 'CARDIOVASCULAR',            metricLabel: `SBP (${UNITS.bp})`,    metricKey: 'sbp' },
  { type: 'cerebrovascular',name: '당뇨병성 뇌혈관 질환',  englishName: 'CEREBROVASCULAR DISEASE',   metricLabel: `BMI (${UNITS.bmi})`,   metricKey: 'bmi' },
  { type: 'dementia',       name: '당뇨병성 치매',         englishName: 'DIABETES-RELATED DEMENTIA', metricLabel: '나이 (세)',            metricKey: 'age' },
];

export const modelNameMap = {
  kidney: 'kidney_disease',
  retinopathy: 'retinopathy',
  cardiovascular: 'cardiovascular',
  neuropathy: 'neuropathy',
  dementia: 'dementia',
  cerebrovascular: 'cerebrovascular',
};

// 주요 위험 요인 패널 (정상 reference 범위 기준 이탈도 바)
export const riskFactors = [
  { label: 'C-peptide', unit: UNITS.cpeptide, key: 'c_peptide', ref: [1.0, 3.5], normalLabel: '1.0–3.5 ng/mL' },
  { label: 'HbA1c',     unit: UNITS.percent,  key: 'hba1c',     ref: [0, 7.0],   normalLabel: '< 7%' },
  { label: '공복혈당',  unit: UNITS.glucose,  key: 'fbg',       ref: [0, 126],   normalLabel: '< 126 mg/dL' },
  { label: 'SBP',       unit: UNITS.bp,       key: 'sbp',       ref: [0, 140],   normalLabel: '< 140 mmHg' },
  { label: 'BMI',       unit: UNITS.bmi,      key: 'bmi',       ref: [18.5, 25], normalLabel: '18.5–25 kg/m²' },
  { label: 'eGFR',      unit: UNITS.egfr,     key: 'eGFR',      ref: [60, 120],  normalLabel: '≥ 60 mL/min' },
  { label: '나이',      unit: '세',           key: 'age',       ref: [0, 65],    normalLabel: '–' },
];

// 질환별 임상 핵심 변수 (1순위 요인 휴리스틱)
export const TOP_FACTOR_DEFS = {
  kidney_disease: [
    { key: 'eGFR', label: 'eGFR', unit: ' mL/min', limit: 60, dir: 'low' },
    { key: 'cr', label: '크레아티닌', unit: ' mg/dL', limit: 1.2, dir: 'high' },
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
    { key: 'sbp', label: '수축기혈압', unit: ' mmHg', limit: 140, dir: 'high' },
  ],
  retinopathy: [
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
    { key: 'c_peptide', label: 'C-peptide', unit: ' ng/mL', limit: 1.0, dir: 'low' },
    { key: 'tg', label: '중성지방', unit: ' mg/dL', limit: 200, dir: 'high' },
  ],
  cardiovascular: [
    { key: 'sbp', label: '수축기혈압', unit: ' mmHg', limit: 140, dir: 'high' },
    { key: 'ldl', label: 'LDL', unit: ' mg/dL', limit: 130, dir: 'high' },
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
    { key: 'hdl', label: 'HDL', unit: ' mg/dL', limit: 40, dir: 'low' },
  ],
  neuropathy: [
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
    { key: 'hdl', label: 'HDL', unit: ' mg/dL', limit: 40, dir: 'low' },
  ],
  cerebrovascular: [
    { key: 'sbp', label: '수축기혈압', unit: ' mmHg', limit: 140, dir: 'high' },
    { key: 'bmi', label: 'BMI', unit: '', limit: 25, dir: 'high' },
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
  ],
  dementia: [
    // 스펙(CLAUDE.md)의 치매 카드 대표 지표는 '나이'. 65세 이상에서 위험이 급증한다.
    { key: 'age', label: '나이', unit: '세', limit: 65, dir: 'high' },
    { key: 'hba1c', label: 'HbA1c', unit: '%', limit: 7.0, dir: 'high' },
    { key: 'sbp', label: '수축기혈압', unit: ' mmHg', limit: 140, dir: 'high' },
  ],
};

// 위험도 1위 합병증의 '주요 영향 지표' (정상범위 최대 이탈 1개)
export function topRiskFactor(diseaseKey, valOf) {
  const defs = TOP_FACTOR_DEFS[diseaseKey];
  if (!defs) return null;
  let best = null;
  for (const d of defs) {
    const v = valOf(d.key);
    if (v == null || !Number.isFinite(v)) continue;
    const dev = d.dir === 'high' ? (v - d.limit) / d.limit : (d.limit - v) / d.limit;
    if (!best || dev > best.dev) {
      best = {
        label: d.label, value: v, unit: d.unit, dev,
        range: d.dir === 'high' ? `${d.limit} 이하` : `${d.limit} 이상`,
        abnormal: dev > 0,
      };
    }
  }
  return best;
}

// 합병증 카드 1순위 지표: 뚜렷한 이탈(>5%) 지표, 없으면 질환 대표 지표
// CLAUDE.md 스펙이 지정한 '카드별 대표 지표' — 질환마다 임상적으로 고유한 지표를 보여준다.
//   (신장=eGFR / 심혈관=수축기혈압 / 뇌혈관=BMI / 신경=HDL / 치매=나이 / 망막=HbA1c)
const CARD_PRIMARY_KEY = {
  kidney_disease: 'eGFR',
  cardiovascular: 'sbp',
  cerebrovascular: 'bmi',
  neuropathy: 'hdl',
  dementia: 'age',
  retinopathy: 'hba1c',
};

export function diseaseCardMetric(diseaseKey, valOf) {
  const defs = TOP_FACTOR_DEFS[diseaseKey];
  if (!defs) return null;

  // 스펙 지정 지표를 우선한다. 이전에는 '이탈률(dev) 최대' 하나만 골라서, HbA1c 가 크게
  // 벗어난 환자는 6개 카드가 전부 'HbA1c 11.2%' 로 똑같이 표시됐다('합병증별 1순위 요인'
  // 이라는 제목·스펙과 모순). 대표 지표 값이 없을 때만 이탈률 최대 지표로 대체한다.
  const primaryKey = CARD_PRIMARY_KEY[diseaseKey];
  const primaryDef = primaryKey ? defs.find((d) => d.key === primaryKey) : null;
  if (primaryDef) {
    const pv = valOf(primaryDef.key);
    if (pv != null && Number.isFinite(pv)) {
      const rounded = Math.abs(pv) >= 100 ? Math.round(pv) : Math.round(pv * 10) / 10;
      return { label: primaryDef.label, value: rounded, unit: primaryDef.unit };
    }
  }

  let best = null;
  for (const d of defs) {
    const v = valOf(d.key);
    if (v == null || !Number.isFinite(v)) continue;
    const dev = d.dir === 'high' ? (v - d.limit) / d.limit : (d.limit - v) / d.limit;
    if (!best || dev > best.dev) best = { def: d, value: v, dev };
  }
  if (!best) return null;
  const v = best.value;
  const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10;
  return { label: best.def.label, value: rounded, unit: best.def.unit };
}

// 지표별 위험 방향 정규화 (0~100%)
export function riskPct(key, value, ref) {
  if (value == null || value === '') return 0;
  const v = Number(value); if (!Number.isFinite(v)) return 0;
  const [lo, hi] = ref;
  if (key === 'c_peptide') {
    if (v < lo) return Math.min(100, (1 - v / lo) * 100);
    if (v > hi) return Math.min(100, ((v - hi) / hi) * 80 + 40);
    return 25;
  }
  if (key === 'eGFR') {
    if (v >= hi) return 10;
    if (v >= lo) return 30;
    return Math.min(100, ((lo - v) / lo) * 100);
  }
  if (key === 'bmi') {
    if (v >= lo && v <= hi) return 20;
    if (v > hi) return Math.min(100, ((v - hi) / hi) * 200 + 40);
    return Math.min(100, ((lo - v) / lo) * 100);
  }
  if (key === 'age') {
    return Math.min(100, (v / 100) * 100);
  }
  if (v <= hi) return Math.max(10, (v / hi) * 40);
  return Math.min(100, ((v - hi) / hi) * 200 + 40);
}

// CKD-EPI 간이 eGFR (Cr + age + sex)
export function calcEGFR(cr, age, sex) {
  if (!cr || !age) return null;
  const s = String(sex).trim().toUpperCase();
  const isMale = (s === 'M' || s === '1' || s === '남' || s === '남자' || s === 'MALE');
  const isFemale = (s === 'F' || s === '2' || s === '여' || s === '여자' || s === 'FEMALE');
  if (!isMale && !isFemale) return null;
  const kappa = isMale ? 0.9 : 0.7;
  const alpha = isMale ? -0.411 : -0.329;
  const factor = isMale ? 1.0 : 1.018;
  const ratio = cr / kappa;
  return Math.round(
    141 * Math.pow(Math.min(ratio, 1), alpha) *
    Math.pow(Math.max(ratio, 1), -1.209) *
    Math.pow(0.993, age) * factor
  );
}

// 환자 객체 → 지표 조회 함수 (1순위 요인/패널 공용). egfr 은 백엔드 단일소스 우선.
export function buildFactorVal(p, egfr) {
  return (key) => {
    const m = {
      eGFR: egfr, cr: p.cr, hba1c: p.hba1c, sbp: p.sbp,
      c_peptide: p.c_peptide, tg: p.triglycerides, ldl: (p.ldl ?? p.ldl_calc),
      hdl: p.hdl, bmi: p.bmi, age: p.age,
    };
    const v = m[key];
    return (v == null || v === '') ? null : Number(v);
  };
}

// 주요 위험 요인 패널용 값 조회 (결측은 null)
export function buildRiskFactorVal(p, egfr) {
  return (key) => {
    const m = {
      c_peptide: p.c_peptide, hba1c: p.hba1c, fbg: p.fbg,
      sbp: p.sbp, bmi: p.bmi, eGFR: egfr, age: p.age,
    };
    const v = m[key];
    return (v == null || v === '') ? null : Number(v);
  };
}
