import { Link } from 'react-router-dom';
import { Upload, FileSpreadsheet, Users } from 'lucide-react';

/**
 * Page-gate empty state.
 * Default: prompts CSV upload (used when patient count = 0).
 * Override `ctaTo`/`ctaLabel`/`icon` for other contexts (e.g. patient-select).
 */
export default function EmptyState({
  title = '\uBA3C\uC800 CSV \uB370\uC774\uD130\uB97C \uC5C5\uB85C\uB4DC\uD574\uC8FC\uC138\uC694',
  message = '\uD658\uC790 \uB370\uC774\uD130\uAC00 \uC5C6\uC5B4 \uC774 \uD398\uC774\uC9C0\uB97C \uC774\uC6A9\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. \uC88C\uCE21 \uC0C1\uB2E8 CSV \uC5C5\uB85C\uB4DC\uC5D0\uC11C \uD658\uC790 \uB370\uC774\uD130\uB97C \uB4F1\uB85D\uD558\uBA74 \uBAA8\uB4E0 \uAE30\uB2A5\uC774 \uD65C\uC131\uD654\uB429\uB2C8\uB2E4.',
  ctaTo = '/home',
  ctaLabel = 'CSV \uC5C5\uB85C\uB4DC \uD398\uC774\uC9C0\uB85C \uC774\uB3D9',
  icon = 'csv', // 'csv' | 'users'
}) {
  const Icon = icon === 'users' ? Users : FileSpreadsheet;
  const CtaIcon = icon === 'users' ? Users : Upload;
  return (
    <div className="flex-1 min-h-[500px] w-full flex items-center justify-center p-6 fade-in">
      <div className="w-full max-w-3xl rounded-2xl border border-dashed border-gray-300 bg-white/70 p-12 text-center shadow-sm">
        <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-accent-soft">
          <Icon className="h-10 w-10 text-accent" strokeWidth={1.4} />
        </div>
        <h2 className="mb-3 text-2xl font-bold text-gray-900 tracking-tight">{title}</h2>
        <p className="mb-8 text-sm leading-relaxed text-gray-500">{message}</p>
        <Link
          to={ctaTo}
          className="inline-flex items-center gap-2 rounded-xl bg-accent hover:bg-accent-dark px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors"
        >
          <CtaIcon className="h-4 w-4" />
          {ctaLabel}
        </Link>
      </div>
    </div>
  );
}
