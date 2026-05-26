# -*- coding: utf-8 -*-
"""
DangBom 프로젝트 - 전체 모델 사용 변수표 (엑셀 1파일, 시트별 모델)
시트 1: CVD (심혈관 합병증 예측 모델 v4)
시트 2: DKD 메인 (신장질환 의사진단 예측)
시트 3: DKD 검사기반 (eGFR<60 / UACR>=30 예측)
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()

# ── 공통 스타일 ──
thin = Side(style='thin', color='AAAAAA')
border_thin = Border(left=thin, right=thin, top=thin, bottom=thin)
border_hdr = Border(
    left=Side(style='medium', color='333333'),
    right=Side(style='medium', color='333333'),
    top=Side(style='medium', color='333333'),
    bottom=Side(style='medium', color='333333'),
)
font_title = Font(name='맑은 고딕', bold=True, size=13, color='FFFFFF')
font_sub   = Font(name='맑은 고딕', size=9, color='FFFFFF', italic=True)
font_hdr   = Font(name='맑은 고딕', bold=True, size=10, color='FFFFFF')
font_sec   = Font(name='맑은 고딕', bold=True, size=10, color='FFFFFF')
font_no    = Font(name='맑은 고딕', size=9, color='595959')
font_var   = Font(name='Courier New', size=9, color='00008B')
font_body  = Font(name='맑은 고딕', size=9)
font_note  = Font(name='맑은 고딕', size=8, italic=True, color='595959')
font_drop  = Font(name='맑은 고딕', size=9, italic=True, color='999999')

fill_row_even = PatternFill('solid', fgColor='EBF3FB')
fill_row_odd  = PatternFill('solid', fgColor='FFFFFF')
fill_derived  = PatternFill('solid', fgColor='E2EFDA')
fill_miss     = PatternFill('solid', fgColor='F2F2F2')
fill_new      = PatternFill('solid', fgColor='FFF2CC')
fill_drop     = PatternFill('solid', fgColor='FFF0F0')

align_c = Alignment(horizontal='center', vertical='center', wrap_text=True)
align_l = Alignment(horizontal='left', vertical='center', wrap_text=True)


def write_sheet(ws, title, subtitle, title_color, hdr_color, sec_colors, rows_data, col_widths, note_lines=None):
    """범용 시트 작성 함수"""
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    n_cols = len(col_widths)

    # 제목
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = font_title; c.fill = PatternFill('solid', fgColor=title_color)
    c.alignment = align_c; c.border = border_hdr
    ws.row_dimensions[1].height = 28

    # 부제목
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font = font_sub; c.fill = PatternFill('solid', fgColor=hdr_color)
    c.alignment = align_c
    ws.row_dimensions[2].height = 16

    # 헤더
    headers = ['No.', '변수명', '변수 내용', 'Value / 단위·코딩']
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=3, column=ci, value=h)
        c.font = font_hdr; c.fill = PatternFill('solid', fgColor=hdr_color)
        c.alignment = align_c; c.border = border_hdr
    ws.row_dimensions[3].height = 20

    row_idx = 4
    var_no = 0
    cur_sec = ''

    for r in rows_data:
        rtype = r[0]
        if rtype == '__SEC__':
            cur_sec = r[1]
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
            c = ws.cell(row=row_idx, column=1, value=f'▶  {cur_sec}')
            c.font = font_sec
            c.fill = PatternFill('solid', fgColor=sec_colors.get(cur_sec, hdr_color))
            c.alignment = align_l; c.border = border_hdr
            ws.row_dimensions[row_idx].height = 18
            row_idx += 1
        else:
            var_no += 1
            _, vname, vdesc, val_unit = r[:4]
            style_hint = r[4] if len(r) > 4 else 'normal'

            if style_hint == 'derived':
                row_fill = fill_derived
            elif style_hint == 'missing':
                row_fill = fill_miss
            elif style_hint == 'new':
                row_fill = fill_new
            elif style_hint == 'drop':
                row_fill = fill_drop
            else:
                row_fill = fill_row_even if var_no % 2 == 0 else fill_row_odd

            vfont = font_drop if style_hint == 'drop' else font_var

            vals = [var_no, vname, vdesc, val_unit]
            fonts_l = [font_no, vfont, font_body, font_body]
            aligns_l = [align_c, align_l, align_l, align_l]

            for ci, (val, fnt, aln) in enumerate(zip(vals, fonts_l, aligns_l), 1):
                c = ws.cell(row=row_idx, column=ci, value=val)
                c.font = fnt; c.fill = row_fill; c.alignment = aln; c.border = border_thin
            ws.row_dimensions[row_idx].height = 26
            row_idx += 1

    # 범례/노트
    if note_lines:
        row_idx += 1
        for note in note_lines:
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
            ws.cell(row=row_idx, column=1, value=note).font = font_note
            ws.cell(row=row_idx, column=1).alignment = align_l
            ws.row_dimensions[row_idx].height = 16
            row_idx += 1


# ═══════════════════════════════════════════════════════════
# 시트 1: CVD (심혈관 합병증)
# ═══════════════════════════════════════════════════════════
ws_cvd = wb.active
ws_cvd.title = 'CVD 심혈관'

cvd_rows = []
S = lambda name: cvd_rows.append(('__SEC__', name))
V = lambda name, desc, val, style='normal': cvd_rows.append(('__VAR__', name, desc, val, style))

S('종속변수')
V('target_cvd', '심혈관질환 발생 여부 (예측 대상)', '0=정상, 1=심혈관질환(협심증/심근경색/뇌졸중/심부전/심방세동 중 >=1)')

S('인구사회학적 변수')
V('age',                              '나이',                  '연속 (세)')
V('sex_code_raw',                     '성별',                  '1=남성, 2=여성')
V('income_household_q_ord',           '가구소득 분위',          '1(하)~4(상) 분위')
V('education_level_ord',              '교육수준',              '1=무학~4=대졸이상')
V('occupation_code_raw',              '직업분류 코드',          '1~10 직업코드')
V('household_generation_code_raw',    '가구세대유형',           '1=1세대~6=비가족')
V('single_person_household_binary',   '1인가구 여부',          '0=아니오, 1=예')
V('household_size',                   '가구원수',              '연속 (명)')

S('생활습관 변수')
V('alcohol_frequency_combined',  '음주 빈도',                  '0=비음주~6=매일')
V('pa_aerobic_code',             '유산소 신체활동 충족 여부',    '0=불충분, 1=충분(주150분 이상)')
V('obesity_prevalence_code',     '비만 단계',                   '1=정상, 2=과체중(BMI>=23), 3=비만(BMI>=25)')
V('stress_high_binary',          '고스트레스 여부',             '0=낮음, 1=높음')
V('depressive_mood_binary',      '우울감 경험 여부',            '0=없음, 1=있음(2주 이상)')
V('avg_sleep_hours',             '하루 평균 수면시간 (v4 신규)\n= (평일수면x5 + 주말수면x2) / 7', '연속 (시간/일)', 'new')

S('신체계측 변수')
V('HE_wc',  '허리둘레 (v3 신규)', '연속 (cm)', 'new')

S('혈압 변수')
V('sbp',                    '수축기 혈압 (평균)',          '연속 (mmHg)')
V('dbp',                    '이완기 혈압 (평균)',          '연속 (mmHg)')
V('hypertension_bp140_90',  '혈압기준 고혈압 여부',        '0=아니오(SBP<140 & DBP<90), 1=예')

S('혈액·생화학 변수')
V('fpg',                      '공복혈당',                   '연속 (mg/dL)')
V('hba1c_harmonized',         '당화혈색소 (HbA1c)',          '연속 (%)')
V('total_cholesterol',        '총콜레스테롤',                '연속 (mg/dL)')
V('hdl_cholesterol',          'HDL 콜레스테롤',              '연속 (mg/dL)')
V('triglycerides_harmonized', '중성지방 (TG)',               '연속 (mg/dL)')
V('hemoglobin',               '혈색소',                     '연속 (g/dL)')
V('uric_acid_mg_dl',          '요산',                       '연속 (mg/dL)')
V('ast_harmonized',           'AST (GOT)',                  '연속 (IU/L)')
V('alt_harmonized',           'ALT (GPT)',                  '연속 (IU/L)')
V('egfr_ckdepi_2021',         '추정사구체여과율 (eGFR)',      '연속 (mL/min/1.73m²) — CKD-EPI 2021 공식')
V('uacr_mg_g',                'UACR (요알부민/크레아티닌)',    '연속 (mg/g)')

S('기저질환 변수')
V('dm_insulin_binary',                  '인슐린 치료 여부',              '0=아니오, 1=예')
V('dm_med_binary',                      '당뇨 경구약 복용 여부',         '0=아니오, 1=예')
V('dm_treatment_any',                   '당뇨 치료 여부 (약물 또는 인슐린)', '0=아니오, 1=예')
V('htn_physician_dx_binary',            '고혈압 의사 진단 여부',          '0=아니오, 1=예')
V('dyslipidemia_physician_dx_binary',   '이상지질혈증 의사 진단 여부',    '0=아니오, 1=예')
V('kidney_physician_dx_binary',         '만성신장질환 의사 진단 여부',    '0=아니오, 1=예')
V('proteinuria_dipstick_ord',           '요시험지봉 단백뇨',             '0=음성~4=4+ (반정량)')
V('metabolic_syndrome_binary',          '대사증후군 여부',               '0=아니오, 1=예')

S('v3 신규 원시변수')
V('dm_duration',   '당뇨 유병기간 (= 현재나이 - 진단나이)',   '연속 (년)', 'new')
V('htn_treatment', '고혈압 약물 치료 여부',                   '0=아니오, 1=예', 'new')

S('영양 변수')
V('breakfast_freq_weekly',  '주간 아침식사 횟수',  '연속 (회/주, 0~7)')
V('lunch_freq_weekly',      '주간 점심식사 횟수',  '연속 (회/주, 0~7)')
V('dinner_freq_weekly',     '주간 저녁식사 횟수',  '연속 (회/주, 0~7)')
V('energy_kcal',            '에너지 섭취량',       '연속 (kcal/일)')
V('protein_g',              '단백질 섭취량',       '연속 (g/일)')
V('fat_g',                  '지방 섭취량',         '연속 (g/일)')
V('sodium_mg',              '나트륨 섭취량',       '연속 (mg/일)')
V('potassium_mg',           '칼륨 섭취량',         '연속 (mg/일)')

S('파생변수')
V('pulse_pressure',       '맥압 = SBP - DBP',                       '연속 (mmHg)', 'derived')
V('non_hdl_cholesterol',  '비HDL 콜레스테롤 = TC - HDL',             '연속 (mg/dL)', 'derived')
V('ldl_friedewald',       'Friedewald LDL = TC - HDL - TG/5 (TG<400)',  '연속 (mg/dL) — 커버율 97.5%', 'derived')
V('ldl_hdl_ratio',        'LDL/HDL 비율',                            '연속 (무단위)', 'derived')
V('age_sq',               '나이 비선형 항 = (age/10)^2',              '연속', 'derived')
V('age_x_htn',            '나이 x 고혈압 진단 상호작용',              '연속', 'derived')
V('age_x_egfr',           '나이 x eGFR / 1000',                      '연속', 'derived')
V('egfr_stage',           'eGFR 기반 CKD 단계 (G1~G5)',               '1(>=90)~5(<15) 순서형', 'derived')
V('egfr_lt60',            'eGFR < 60 여부 (CKD G3 이상)',              '0=아니오, 1=예', 'derived')
V('age_x_egfr_lt60',      '나이 x (eGFR<60)',                         '연속', 'derived')
V('ldl_x_egfr',           'Friedewald LDL x eGFR / 10000',            '연속', 'derived')
V('social_risk',          '사회경제 위험 복합지수 = -소득-교육+스트레스+우울', '연속 (높을수록 위험)', 'derived')
V('sbp_x_pp',             '수축기혈압 x 맥압 / 10000',                '연속', 'derived')
V('uacr_log',             'log(UACR + 1)',                             '연속 (log-변환)', 'derived')
V('waist_x_age',          '허리둘레 x 나이 / 1000 (v3)',               '연속', 'derived')
V('dm_duration_sq',       '당뇨 유병기간 제곱 = (dm_duration/5)^2 (v3)', '연속', 'derived')
V('dm_long_duration',     '당뇨 유병기간 >= 10년 여부 (v3)',             '0=아니오, 1=예', 'derived')
V('htn_treat_x_age',      '고혈압 치료 x 나이 (v3)',                    '연속', 'derived')

S('결측지시변수 (Missing Indicator)')
miss_vars_cvd = [
    'age','sbp','dbp','fpg','hba1c_harmonized','total_cholesterol',
    'ldl_cholesterol','hdl_cholesterol','triglycerides_harmonized',
    'hemoglobin','uric_acid_mg_dl','hscrp_mg_l','ast_harmonized','alt_harmonized',
    'egfr_ckdepi_2021','uacr_mg_g','sodium_potassium_ratio',
    'household_size',
    'breakfast_freq_weekly','lunch_freq_weekly','dinner_freq_weekly',
    'energy_kcal','carbohydrate_g','protein_g','fat_g',
    'sodium_mg','potassium_mg','dietary_fiber_g','sugar_g',
    'waist','dm_duration','avg_sleep',
]
for mv in miss_vars_cvd:
    V(f'{mv}_missing', f'{mv} 원본 결측 지시', '0=관측됨, 1=원본 결측 -> 중앙값 대체', 'missing')

cvd_sec_colors = {
    '종속변수':          '1F497D',
    '인구사회학적 변수':  '366092',
    '생활습관 변수':      '4472C4',
    '신체계측 변수':      '5B9BD5',
    '혈압 변수':          '2E75B6',
    '혈액·생화학 변수':   '4472C4',
    '기저질환 변수':      '366092',
    'v3 신규 원시변수':   '843C0C',
    '영양 변수':          '366092',
    '파생변수':           '375623',
    '결측지시변수 (Missing Indicator)': '595959',
}

write_sheet(
    ws_cvd,
    title='심혈관 합병증(CVD) 예측 모델 v4 - 사용 변수표',
    subtitle='대상: 당뇨병 환자 | EasyEnsembleClassifier | KNHANES 2019~2024 | Validation AUC: 0.660',
    title_color='1F3864', hdr_color='2E75B6',
    sec_colors=cvd_sec_colors,
    rows_data=cvd_rows,
    col_widths=[5, 38, 42, 50],
    note_lines=[
        '※ 범례: 노란 배경=v3/v4 신규변수 | 초록 배경=파생변수 | 회색 배경=결측지시변수',
        '※ v4 변경: avg_sleep_hours(수면 통합), atherogenic_index/eating_out/breakfast_skip/dinner_skip 제거',
        '※ 제거 변수(모델 미사용): bmi, ldl_cholesterol(61% 결측), hscrp_mg_l(73% 결측), survey_year, married_spouse_present 등',
    ],
)


# ═══════════════════════════════════════════════════════════
# 시트 2: DKD 메인 (신장질환 의사진단)
# ═══════════════════════════════════════════════════════════
ws_kid = wb.create_sheet('DKD 메인(의사진단)')

kid_rows = []
S = lambda name: kid_rows.append(('__SEC__', name))
V = lambda name, desc, val, style='normal': kid_rows.append(('__VAR__', name, desc, val, style))

S('종속변수')
V('target_dkd', '신장질환 의사진단 여부 (예측 대상)', '0=없음, 1=있음 (콩팥병 의사 진단)')

S('기본 정보')
V('age',          '나이',   '연속 (세)')
V('bmi',          'BMI',    '연속 (kg/m²)')
V('sex_code_raw', '성별',   '1=남성, 2=여성')

S('사회경제적 변수')
V('income_household_q_ord',   '가구소득 분위',      '1(하)~4(상) 분위')
V('education_level_ord',      '교육수준',           '1=무학~4=대졸이상')
V('married_spouse_present',   '배우자 유무',         '0=없음, 1=있음')
V('survey_year',              '조사연도',            '2019~2024')

S('생활습관 변수')
V('current_smoker_binary',       '현재 흡연 여부',           '0=아니오, 1=예')
V('alcohol_frequency_combined',  '음주 빈도',               '0=비음주~6=매일')
V('pa_aerobic_code',             '유산소 신체활동 충족 여부', '0=불충분, 1=충분')
V('obesity_prevalence_code',     '비만 단계',                '1=정상, 2=과체중, 3=비만')

S('혈압 변수')
V('sbp',                    '수축기 혈압',           '연속 (mmHg)')
V('dbp',                    '이완기 혈압',           '연속 (mmHg)')
V('hypertension_bp140_90',  '혈압기준 고혈압 여부',   '0=아니오, 1=예 (SBP>=140 또는 DBP>=90)')

S('혈액·생화학 변수')
V('fpg',                      '공복혈당',              '연속 (mg/dL)')
V('hba1c_harmonized',         '당화혈색소 (HbA1c)',     '연속 (%)')
V('total_cholesterol',        '총콜레스테롤',           '연속 (mg/dL)')
V('hdl_cholesterol',          'HDL 콜레스테롤',         '연속 (mg/dL)')
V('triglycerides_harmonized', '중성지방 (TG)',          '연속 (mg/dL)')
V('hemoglobin',               '혈색소',                '연속 (g/dL)')
V('ast_harmonized',           'AST (GOT)',             '연속 (IU/L)')
V('alt_harmonized',           'ALT (GPT)',             '연속 (IU/L)')

S('신장 기능 변수')
V('egfr_ckdepi_2021',        '추정사구체여과율 (eGFR)', '연속 (mL/min/1.73m²) — CKD-EPI 2021')
V('uacr_mg_g',               'UACR (요알부민/크레아티닌)', '연속 (mg/g)')
V('proteinuria_dipstick_ord','요시험지봉 단백뇨',       '0=음성~4=4+ (반정량)')

S('당뇨 관련 변수')
V('dm_insulin_binary',  '인슐린 치료 여부',  '0=아니오, 1=예')
V('dm_med_binary',      '당뇨 경구약 복용',  '0=아니오, 1=예')
V('dm_physician_dx_binary (제거)',   '당뇨 의사진단 (상수=1, 제거)',   '모두 1 → 정보 없음, 모델 제거', 'drop')
V('dm_current_status_binary (제거)', '현재 당뇨 상태 (준상수, 제거)',   '97%+ 동일값 → 제거', 'drop')
V('dm_treatment_any (제거)',         '당뇨 치료 여부 (제거)',           '복합변수, 중요도=0 → 제거', 'drop')
V('dm_final_positive (제거)',        '당뇨 최종 양성 (상수=1, 제거)',   '모두 1 → 정보 없음, 모델 제거', 'drop')

S('영양 섭취 변수')
V('energy_kcal',     '에너지 섭취량',    '연속 (kcal/일)')
V('carbohydrate_g',  '탄수화물 섭취량',  '연속 (g/일)')
V('protein_g',       '단백질 섭취량',    '연속 (g/일)')
V('fat_g',           '지방 섭취량',      '연속 (g/일)')
V('sodium_mg',       '나트륨 섭취량',    '연속 (mg/일)')
V('potassium_mg',    '칼륨 섭취량',      '연속 (mg/일)')
V('dietary_fiber_g', '식이섬유 섭취량',  '연속 (g/일)')
V('sugar_g',         '당류 섭취량',      '연속 (g/일)')

S('결측지시변수 (Missing Indicator)')
miss_vars_kid = [
    'fpg','hba1c_harmonized','total_cholesterol','hdl_cholesterol',
    'triglycerides_harmonized','hemoglobin','ast_harmonized','alt_harmonized',
    'energy_kcal','carbohydrate_g','protein_g','fat_g',
    'sodium_mg','potassium_mg','dietary_fiber_g','sugar_g',
    'egfr_ckdepi_2021','uacr_mg_g',
]
for mv in miss_vars_kid:
    V(f'{mv}_missing', f'{mv} 원본 결측 지시', '0=관측됨, 1=원본 결측 -> 중앙값 대체', 'missing')

V('age_missing (제거)',  '나이 결측 지시 (중요도=0, 제거)',  '제거', 'drop')
V('bmi_missing (제거)',  'BMI 결측 지시 (중요도=0, 제거)',   '제거', 'drop')
V('sbp_missing (제거)',  'SBP 결측 지시 (중요도=0, 제거)',   '제거', 'drop')
V('dbp_missing (제거)',  'DBP 결측 지시 (중요도=0, 제거)',   '제거', 'drop')

kid_sec_colors = {
    '종속변수':          '1A4A7A',
    '기본 정보':         '366092',
    '사회경제적 변수':    '4472C4',
    '생활습관 변수':      '5B9BD5',
    '혈압 변수':          '2E75B6',
    '혈액·생화학 변수':   '4472C4',
    '신장 기능 변수':     '843C0C',
    '당뇨 관련 변수':     '7F0000',
    '영양 섭취 변수':     '375623',
    '결측지시변수 (Missing Indicator)': '595959',
}

write_sheet(
    ws_kid,
    title='당뇨병성 신장질환(DKD) 메인 모델 - 사용 변수표',
    subtitle='대상: 당뇨병 환자 | 종속변수: 콩팥병 의사진단 | EasyEnsembleClassifier | AUC: 0.829 | NPV: 0.985',
    title_color='1A4A7A', hdr_color='2E75B6',
    sec_colors=kid_sec_colors,
    rows_data=kid_rows,
    col_widths=[5, 42, 42, 50],
    note_lines=[
        '※ 분홍 배경=제거 변수(상수/준상수/중요도=0) | 회색 배경=결측지시변수',
        '※ 제거 변수(8개): dm_physician_dx_binary, dm_current_status_binary, dm_final_positive, dm_treatment_any, age_missing, bmi_missing, sbp_missing, dbp_missing',
    ],
)


# ═══════════════════════════════════════════════════════════
# 시트 3: DKD 검사기반 (eGFR<60 / UACR>=30)
# ═══════════════════════════════════════════════════════════
ws_lab = wb.create_sheet('DKD 검사기반')

lab_rows = []
S = lambda name: lab_rows.append(('__SEC__', name))
V = lambda name, desc, val, style='normal': lab_rows.append(('__VAR__', name, desc, val, style))

S('종속변수')
V('target_dkd', 'DKD 여부 (검사기반 정의)', '0=정상, 1=DKD (eGFR<60 또는 UACR>=30)')

S('기본 정보')
V('age',          '나이',  '연속 (세)')
V('bmi',          'BMI',   '연속 (kg/m²)')
V('sex_code_raw', '성별',  '1=남성, 2=여성')

S('사회경제적 변수')
V('income_household_q_ord',  '가구소득 분위',  '1(하)~4(상) 분위')
V('education_level_ord',     '교육수준',       '1=무학~4=대졸이상')
V('married_spouse_present',  '배우자 유무',     '0=없음, 1=있음')
V('survey_year',             '조사연도',        '2019~2024')

S('생활습관 변수')
V('current_smoker_binary',       '현재 흡연 여부',           '0=아니오, 1=예')
V('alcohol_frequency_combined',  '음주 빈도',               '0=비음주~6=매일')
V('pa_aerobic_code',             '유산소 신체활동 충족 여부', '0=불충분, 1=충분')
V('obesity_prevalence_code',     '비만 단계',                '1=정상, 2=과체중, 3=비만')

S('혈압 변수')
V('sbp',                    '수축기 혈압',          '연속 (mmHg)')
V('dbp',                    '이완기 혈압',          '연속 (mmHg)')
V('hypertension_bp140_90',  '혈압기준 고혈압 여부',  '0=아니오, 1=예')

S('혈액·생화학 변수')
V('fpg',                      '공복혈당',              '연속 (mg/dL)')
V('hba1c_harmonized',         '당화혈색소 (HbA1c)',     '연속 (%)')
V('total_cholesterol',        '총콜레스테롤',           '연속 (mg/dL)')
V('hdl_cholesterol',          'HDL 콜레스테롤',         '연속 (mg/dL)')
V('triglycerides_harmonized', '중성지방 (TG)',          '연속 (mg/dL)')
V('hemoglobin',               '혈색소',                '연속 (g/dL)')
V('ast_harmonized',           'AST (GOT)',             '연속 (IU/L)')
V('alt_harmonized',           'ALT (GPT)',             '연속 (IU/L)')

S('당뇨 관련 변수')
V('dm_physician_dx_binary',   '당뇨 의사진단 여부',      '0=아니오, 1=예')
V('dm_current_status_binary', '현재 당뇨 상태',          '0=아니오, 1=예')
V('dm_insulin_binary',        '인슐린 치료 여부',        '0=아니오, 1=예')
V('dm_med_binary',            '당뇨 경구약 복용',        '0=아니오, 1=예')
V('dm_treatment_any',         '당뇨 치료 여부 (약물+인슐린)', '0=아니오, 1=예')
V('dm_final_positive',        '당뇨 최종 양성',          '0=아니오, 1=예')

S('영양 섭취 변수')
V('energy_kcal',     '에너지 섭취량',    '연속 (kcal/일)')
V('carbohydrate_g',  '탄수화물 섭취량',  '연속 (g/일)')
V('protein_g',       '단백질 섭취량',    '연속 (g/일)')
V('fat_g',           '지방 섭취량',      '연속 (g/일)')
V('sodium_mg',       '나트륨 섭취량',    '연속 (mg/일)')
V('potassium_mg',    '칼륨 섭취량',      '연속 (mg/일)')
V('dietary_fiber_g', '식이섬유 섭취량',  '연속 (g/일)')
V('sugar_g',         '당류 섭취량',      '연속 (g/일)')

S('결측지시변수 (Missing Indicator)')
miss_vars_lab = [
    'age','bmi','sbp','dbp',
    'fpg','hba1c_harmonized','total_cholesterol','hdl_cholesterol',
    'triglycerides_harmonized','hemoglobin','ast_harmonized','alt_harmonized',
    'energy_kcal','carbohydrate_g','protein_g','fat_g',
    'sodium_mg','potassium_mg','dietary_fiber_g','sugar_g',
]
for mv in miss_vars_lab:
    V(f'{mv}_missing', f'{mv} 원본 결측 지시', '0=관측됨, 1=원본 결측 -> 중앙값 대체', 'missing')

lab_sec_colors = {
    '종속변수':          '1A4A7A',
    '기본 정보':         '366092',
    '사회경제적 변수':    '4472C4',
    '생활습관 변수':      '5B9BD5',
    '혈압 변수':          '2E75B6',
    '혈액·생화학 변수':   '4472C4',
    '당뇨 관련 변수':     '7F0000',
    '영양 섭취 변수':     '375623',
    '결측지시변수 (Missing Indicator)': '595959',
}

write_sheet(
    ws_lab,
    title='당뇨병성 신장질환(DKD) 검사기반 모델 - 사용 변수표',
    subtitle='대상: 당뇨병 환자 | 종속변수: eGFR<60 또는 UACR>=30 | EasyEnsembleClassifier | AUC: 0.740',
    title_color='1A4A7A', hdr_color='2E75B6',
    sec_colors=lab_sec_colors,
    rows_data=lab_rows,
    col_widths=[5, 42, 42, 50],
    note_lines=[
        '※ 이 모델은 신장 기능 검사값(eGFR, UACR)을 종속변수에 사용했으므로 설명변수에 포함하지 않음',
        '※ 제거 변수 없음 (모든 변수 사용)',
        '※ 회색 배경=결측지시변수',
    ],
)


# ── 저장 ──
out_path = r'C:\DangBom_project\model_variable_tables.xlsx'
wb.save(out_path)
print(f'저장 완료: {out_path}')
print(f'시트: {wb.sheetnames}')
