import { Card } from '@/components/ui/Card';
import { formatCount } from '@/features/building/format';
import { getSectionMessage } from '@/features/building/missingReasonText';
import type { Insight } from '@/types/insight';

interface TradesCardProps {
  insight: Insight;
}

export function TradesCard({ insight }: TradesCardProps) {
  const sectionMessage = getSectionMessage(insight.status, 'trades', insight.missing);

  if (sectionMessage || !insight.trades) {
    return (
      <Card title={sectionMessage?.title ?? '데이터 없음'}>
        <p className="text-sm text-foreground-muted">
          {sectionMessage?.message ?? '데이터를 불러올 수 없어요.'}
        </p>
      </Card>
    );
  }

  const { trades } = insight;
  return (
    <Card title="실거래">
      <p className="text-xs text-foreground-muted">반경 500m, 최근 24개월, 매매 기준</p>
      <p className="mt-2 text-sm">
        거래
        {formatCount(trades.count)}
      </p>
    </Card>
  );
}
