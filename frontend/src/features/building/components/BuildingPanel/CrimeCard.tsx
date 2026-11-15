import { Card } from '@/components/ui/Card';
import { formatArea, formatPercent } from '@/features/building/format';
import { getSectionMessage } from '@/features/building/missingReasonText';
import { layerSlugs } from '@/features/map/layerSlugs';
import { useLayersQuery } from '@/features/map/queries';
import type { Insight } from '@/types/insight';
import type { MapLayer } from '@/types/layer';

interface CrimeCardProps {
  insight: Insight;
}

function selectCrimeHotspotNotice(layers: MapLayer[]): string | null {
  const layer = layers.find((item) => item.slug === layerSlugs.crimeHotspot);
  return layer?.notice ?? null;
}

export function CrimeCard({ insight }: CrimeCardProps) {
  const { data: notice } = useLayersQuery(selectCrimeHotspotNotice);
  const sectionMessage = getSectionMessage(insight.status, 'crime', insight.missing);

  if (sectionMessage || !insight.crime) {
    return (
      <Card title={sectionMessage?.title ?? '데이터 없음'}>
        <p className="text-sm text-foreground-muted">
          {sectionMessage?.message ?? '데이터를 불러올 수 없어요.'}
        </p>
      </Card>
    );
  }

  const { crime } = insight;
  return (
    <Card title="범죄 발생 밀도">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-foreground-muted">최고 등급</dt>
        <dd>
          {crime.max_grad}
          등급
        </dd>
        <dt className="text-foreground-muted">인접 등급</dt>
        <dd>{crime.near_grad !== null ? `${crime.near_grad}등급` : '-'}</dd>
        <dt className="text-foreground-muted">주의구역 면적</dt>
        <dd>{formatArea(crime.flagged_area_m2)}</dd>
        <dt className="text-foreground-muted">고등급 비중</dt>
        <dd>{formatPercent(crime.high_share_pct)}</dd>
        <dt className="text-foreground-muted">데이터 기간</dt>
        <dd>{insight.as_of.crime_data_period ?? '-'}</dd>
      </dl>
      {notice && <p className="mt-2 text-xs text-foreground-muted">{notice}</p>}
    </Card>
  );
}
