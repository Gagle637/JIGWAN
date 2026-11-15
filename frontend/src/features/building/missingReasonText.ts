import type { InsightMissingEntry, InsightStatus } from '@/types/insight';

export interface SectionMessage {
  title: string;
  message: string;
}

const reasonTitles: Record<string, string> = {
  no_crime_segment: '주의구간 미지정',
};

const reasonMessages: Record<string, string> = {
  no_registry_data: '건축물대장에 등록된 정보가 없어요.',
  house_type_unmapped: '주택이 아니거나 용도 정보가 없어 실거래 집계 대상이 아니에요.',
  detached_house_district_not_implemented: '단독·다가구는 지번이 공개되지 않아 주변 시세를 집계할 수 없어요.',
  no_satellite_data: '이 위치의 위성 분석 결과가 아직 없어요.',
  no_crime_segment: '반경 안에 지정된 범죄주의구간이 없어요.',
};

const defaultTitle = '데이터 없음';
const unknownReasonMessage = '데이터를 불러올 수 없어요.';
const satellitePendingMessage = '위성 분석 준비 중이에요.';
const satelliteFields = new Set(['green', 'change']);

export function getSectionMessage(
  status: InsightStatus,
  field: string,
  missing: InsightMissingEntry[],
): SectionMessage | null {
  if (status === 'pending' && satelliteFields.has(field)) {
    return { title: defaultTitle, message: satellitePendingMessage };
  }

  const entry = missing.find((item) => item.field === field);
  if (!entry) return null;

  return {
    title: reasonTitles[entry.reason] ?? defaultTitle,
    message: reasonMessages[entry.reason] ?? unknownReasonMessage,
  };
}
