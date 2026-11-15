import { Card } from '@/components/ui/Card';
import { formatArea, formatDistance } from '@/features/building/format';
import { getSectionMessage } from '@/features/building/missingReasonText';
import type { Insight } from '@/types/insight';

interface ChangeCardProps {
  insight: Insight;
}

const periodLabels: Record<string, string> = {
  '1y': '최근 1년',
  '2y': '최근 2년',
  '3y': '최근 3년',
};

export function ChangeCard({ insight }: ChangeCardProps) {
  const sectionMessage = getSectionMessage(insight.status, 'change', insight.missing);

  if (sectionMessage || !insight.change) {
    return (
      <Card title={sectionMessage?.title ?? '데이터 없음'}>
        <p className="text-sm text-foreground-muted">
          {sectionMessage?.message ?? '데이터를 불러올 수 없어요.'}
        </p>
      </Card>
    );
  }

  const { change } = insight;
  return (
    <Card title="개발 징후">
      <p className="text-sm">
        반경 내 총 변화 면적
        {' '}
        <strong>{formatArea(change.total_area_m2)}</strong>
      </p>
      {change.areas.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-foreground-muted">
          {change.areas.map((area) => (
            <li key={area.id}>
              {formatArea(area.area_m2)}
              {' '}
              ·
              {formatDistance(area.distance_m)}
              {' '}
              ·
              {' '}
              {periodLabels[area.period] ?? area.period}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
