import usePatientCount from '../hooks/usePatientCount';
import EmptyState from '../components/EmptyState';

/**
 * /dashboard route landing (no patientId in URL).
 * - patient count == 0 → CSV upload prompt
 * - patient count > 0  → "환자를 선택하세요" prompt with link to PatientList
 */
export default function DashboardLanding() {
  const { count, loading } = usePatientCount();

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent" />
      </div>
    );
  }

  if (count === 0) {
    return (
      <EmptyState
        title={'\uB300\uC2DC\uBCF4\uB4DC\uB97C \uC774\uC6A9\uD558\uB824\uBA74 CSV\uAC00 \uD544\uC694\uD569\uB2C8\uB2E4'}
        message={'\uD658\uC790 \uB370\uC774\uD130\uB97C \uC5C5\uB85C\uB4DC\uD55C \uB4A4 \uD658\uC790 \uBAA9\uB85D\uC5D0\uC11C \uBD84\uC11D\uD560 \uD658\uC790\uB97C \uC120\uD0DD\uD558\uBA74 \uD569\uBCD1\uC99D \uC704\uD5D8 \uB300\uC2DC\uBCF4\uB4DC\uB97C \uBCFC \uC218 \uC788\uC2B5\uB2C8\uB2E4.'}
      />
    );
  }

  return (
    <EmptyState
      icon="users"
      title={'\uBD84\uC11D\uD560 \uD658\uC790\uB97C \uC120\uD0DD\uD574 \uC8FC\uC138\uC694'}
      message={`\uB4F1\uB85D\uB41C ${count}\uBA85\uC758 \uD658\uC790 \uC911 \uD55C \uBA85\uC744 \uC120\uD0DD\uD558\uBA74 \uD569\uBCD1\uC99D \uC704\uD5D8 \uB300\uC2DC\uBCF4\uB4DC\uAC00 \uC5F4\uB9BD\uB2C8\uB2E4.`}
      ctaTo="/patients"
      ctaLabel={'\uD658\uC790 \uBAA9\uB85D\uC73C\uB85C \uC774\uB3D9'}
    />
  );
}
