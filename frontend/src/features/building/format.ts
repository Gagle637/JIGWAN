const emptyValue = '-';

export function formatPercent(value: number | null, digits = 1): string {
  if (value === null) return emptyValue;
  return `${value.toFixed(digits)}%`;
}

export function formatSignedPercentPoint(value: number | null): string {
  if (value === null) return emptyValue;
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%p`;
}

export function formatArea(value: number | null): string {
  if (value === null) return emptyValue;
  return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}㎡`;
}

export function formatDistance(value: number | null): string {
  if (value === null) return emptyValue;
  return `${value.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}m`;
}

export function formatYears(value: number | null): string {
  if (value === null) return emptyValue;
  return `${value}년`;
}

export function formatDateTime(value: string | null): string {
  if (value === null) return emptyValue;
  const date = new Date(value);
  return date.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatCount(value: number): string {
  return `${value.toLocaleString('ko-KR')}건`;
}
