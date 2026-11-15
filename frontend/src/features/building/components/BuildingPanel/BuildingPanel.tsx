import { ApiError } from '@/api/fetch';
import { Button } from '@/components/ui/Button';
import { formatDateTime } from '@/features/building/format';
import { useInsightQuery } from '@/features/building/queries';
import { useBuildingSelection } from '@/features/building/useBuildingSelection';

import { ChangeCard } from './ChangeCard';
import { CrimeCard } from './CrimeCard';
import { GreenCard } from './GreenCard';
import { SpecCard } from './SpecCard';
import { TradesCard } from './TradesCard';

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'BUILDING_NOT_FOUND') return '건물을 찾을 수 없어요.';
    if (error.code === 'RATE_LIMITED') return '요청이 많아요. 잠시 후 다시 시도해주세요.';
  }
  return '건물 정보를 불러올 수 없어요.';
}

export function BuildingPanel() {
  const { buildingId, radius, setRadius, clear } = useBuildingSelection();
  const { data: insight, isPending, isFetching, isError, error } = useInsightQuery(
    buildingId,
    radius,
  );

  if (buildingId === null) return null;

  return (
    <aside className="absolute top-4 right-4 bottom-4 w-80 overflow-y-auto rounded-md border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          <Button variant={radius === 500 ? 'primary' : 'ghost'} size="sm" onClick={() => setRadius(500)}>
            500m
          </Button>
          <Button variant={radius === 1000 ? 'primary' : 'ghost'} size="sm" onClick={() => setRadius(1000)}>
            1km
          </Button>
        </div>
        <Button variant="ghost" size="sm" onClick={clear}>
          닫기
        </Button>
      </div>

      {isFetching && !isPending && (
        <p className="mt-2 text-xs text-foreground-muted">갱신 중...</p>
      )}

      {isPending && <p className="mt-4 text-sm text-foreground-muted">불러오는 중...</p>}

      {isError && !insight && (
        <p className="mt-4 text-sm text-foreground-muted">{errorMessage(error)}</p>
      )}

      {insight && (
        <>
          <h2 className="mt-3 text-base font-semibold text-foreground">
            {insight.building.name ?? insight.building.address ?? '선택한 건물'}
          </h2>
          <div className="mt-3 space-y-3">
            <SpecCard insight={insight} />
            <GreenCard insight={insight} />
            <ChangeCard insight={insight} />
            <TradesCard insight={insight} />
            <CrimeCard insight={insight} />
          </div>
          <dl className="mt-4 space-y-1 border-t border-border pt-3 text-xs text-foreground-muted">
            <div className="flex justify-between">
              <dt>위성 촬영 기간</dt>
              <dd>{insight.as_of.satellite_period ?? '-'}</dd>
            </div>
            <div className="flex justify-between">
              <dt>실거래 동기화</dt>
              <dd>{formatDateTime(insight.as_of.trade_synced_at)}</dd>
            </div>
            <div className="flex justify-between">
              <dt>범죄 데이터 기간</dt>
              <dd>{insight.as_of.crime_data_period ?? '-'}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-foreground-muted">투자 자문이 아닌 참고 정보입니다.</p>
        </>
      )}
    </aside>
  );
}
