import { Card } from '@/components/ui/Card';
import { formatArea, formatPercent, formatYears } from '@/features/building/format';
import { getSectionMessage } from '@/features/building/missingReasonText';
import type { Insight } from '@/types/insight';

interface SpecCardProps {
  insight: Insight;
}

export function SpecCard({ insight }: SpecCardProps) {
  const sectionMessage = getSectionMessage(insight.status, 'spec', insight.missing);

  if (sectionMessage || !insight.spec) {
    return (
      <Card title={sectionMessage?.title ?? '데이터 없음'}>
        <p className="text-sm text-foreground-muted">
          {sectionMessage?.message ?? '데이터를 불러올 수 없어요.'}
        </p>
      </Card>
    );
  }

  const { spec } = insight;
  return (
    <Card title="건물 스펙">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-foreground-muted">용도</dt>
        <dd>{spec.use ?? '-'}</dd>
        <dt className="text-foreground-muted">대지면적</dt>
        <dd>{formatArea(spec.land_area_m2)}</dd>
        <dt className="text-foreground-muted">연면적</dt>
        <dd>{formatArea(spec.total_floor_area_m2)}</dd>
        <dt className="text-foreground-muted">건폐율</dt>
        <dd>{formatPercent(spec.bcr_pct)}</dd>
        <dt className="text-foreground-muted">용적률</dt>
        <dd>{formatPercent(spec.far_pct)}</dd>
        <dt className="text-foreground-muted">사용승인일</dt>
        <dd>
          {spec.approval_date ?? '-'}
          {' '}
          (
          {formatYears(spec.age_years)}
          )
        </dd>
      </dl>
    </Card>
  );
}
