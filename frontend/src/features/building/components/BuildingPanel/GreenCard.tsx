import { Card } from '@/components/ui/Card';
import { formatPercent, formatSignedPercentPoint } from '@/features/building/format';
import { getSectionMessage } from '@/features/building/missingReasonText';
import type { Insight } from '@/types/insight';

interface GreenCardProps {
  insight: Insight;
}

export function GreenCard({ insight }: GreenCardProps) {
  const sectionMessage = getSectionMessage(insight.status, 'green', insight.missing);

  if (sectionMessage || !insight.green) {
    return (
      <Card title={sectionMessage?.title ?? '데이터 없음'}>
        <p className="text-sm text-foreground-muted">
          {sectionMessage?.message ?? '데이터를 불러올 수 없어요.'}
        </p>
      </Card>
    );
  }

  const { green } = insight;
  return (
    <Card title="녹지">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-foreground-muted">녹지율</dt>
        <dd>{formatPercent(green.ratio_pct)}</dd>
        <dt className="text-foreground-muted">시·구 평균</dt>
        <dd>{formatPercent(green.region_avg_pct)}</dd>
        <dt className="text-foreground-muted">평균 대비</dt>
        <dd>{formatSignedPercentPoint(green.diff_pp)}</dd>
        <dt className="text-foreground-muted">유효 비율</dt>
        <dd>{formatPercent(green.coverage_pct)}</dd>
      </dl>
    </Card>
  );
}
