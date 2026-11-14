import MapCanvas from '../components/map/MapCanvas'

export default function MapPage() {
  return (
    <div className="relative h-full w-full">
      <MapCanvas />

      {/* 검색창 자리 — 내용은 이후 단계에서 채운다. */}
      <div className="pointer-events-none absolute top-4 left-4 h-10 w-80 rounded-md border border-slate-300 bg-white/90" />

      {/* 로그인 자리 — 내용은 인증 단계에서 채운다. */}
      <div className="pointer-events-none absolute top-4 right-4 h-10 w-24 rounded-md border border-slate-300 bg-white/90" />

      {/* 레이어 버튼 자리 — 내용은 다음 단계에서 채운다. */}
      <div className="pointer-events-none absolute bottom-4 left-4 h-10 w-10 rounded-md border border-slate-300 bg-white/90" />

      {/* 접이식 패널 자리 — 내용은 건물 insight 단계에서 채운다. */}
      <div className="pointer-events-none absolute top-16 right-4 bottom-4 w-80 rounded-md border border-slate-300 bg-white/90" />
    </div>
  )
}
