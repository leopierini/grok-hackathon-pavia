export function CornerFrame({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="relative overflow-hidden rounded-xl bg-[#d7e4ee]" role="img" aria-label={label}>
      {children}
      <span className="pointer-events-none absolute left-2 top-2 h-4 w-4 border-l-2 border-t-2 border-white" />
      <span className="pointer-events-none absolute right-2 top-2 h-4 w-4 border-r-2 border-t-2 border-white" />
      <span className="pointer-events-none absolute bottom-2 left-2 h-4 w-4 border-b-2 border-l-2 border-white" />
      <span className="pointer-events-none absolute bottom-2 right-2 h-4 w-4 border-b-2 border-r-2 border-white" />
    </div>
  );
}

export function SurveyScene({ badge = "SIM", person = false, dog = false }: { badge?: string; person?: boolean; dog?: boolean }) {
  return (
    <CornerFrame label={person ? "Simulated forward camera, person visible" : dog ? "Simulated frame of Go2 PRO" : "Simulated site survey view"}>
      <svg viewBox="0 0 640 360" className="aspect-video w-full">
        <rect width="640" height="360" fill="#c5d8e4" />
        <rect x="0" y="0" width="640" height="150" fill="#9fd0ea" />
        <rect x="36" y="78" width="210" height="150" fill="#d7dde3" />
        <rect x="58" y="98" width="36" height="48" fill="#8fb4c9" />
        <rect x="110" y="98" width="36" height="48" fill="#8fb4c9" />
        <rect x="162" y="98" width="36" height="48" fill="#8fb4c9" />
        <path d="M250 228 C310 210 360 250 430 236 C500 222 560 250 640 230 L640 360 L180 360 Z" fill="#c6b89a" />
        <path d="M300 250 C360 236 410 268 470 256 C530 244 580 270 640 252 L640 360 L250 360 Z" fill="#b7a888" />
        <ellipse cx="150" cy="250" rx="90" ry="36" fill="#7ea36a" />
        <ellipse cx="520" cy="230" rx="80" ry="30" fill="#6f9660" />
        {person ? (
          <g>
            <circle cx="330" cy="168" r="16" fill="#2c3440" />
            <path d="M314 188 h32 l8 70 h-48 z" fill="#243042" />
            <path d="M318 210 h24 l6 18 h-36 z" fill="#3d4c63" />
            <rect x="292" y="150" width="76" height="54" fill="none" stroke="#39C7F4" strokeWidth="3" />
          </g>
        ) : null}
        {dog ? (
          <g transform="translate(250 150)">
            <rect x="20" y="40" width="120" height="48" rx="16" fill="#e8eef3" />
            <rect x="78" y="18" width="46" height="36" rx="10" fill="#d5dee6" />
            <rect x="96" y="28" width="22" height="12" rx="3" fill="#17304c" />
            <rect x="28" y="84" width="12" height="36" rx="4" fill="#c5d0da" />
            <rect x="58" y="84" width="12" height="36" rx="4" fill="#c5d0da" />
            <rect x="108" y="84" width="12" height="36" rx="4" fill="#c5d0da" />
            <rect x="136" y="84" width="12" height="36" rx="4" fill="#c5d0da" />
          </g>
        ) : null}
      </svg>
      <span className="absolute left-3 top-3 rounded-md bg-blue px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">{badge}</span>
    </CornerFrame>
  );
}

export function DogMark({ className = "h-16 w-20" }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 80" className={className} aria-hidden>
      <rect x="18" y="28" width="70" height="28" rx="10" fill="#d5dee6" />
      <rect x="58" y="12" width="28" height="22" rx="6" fill="#eef3f7" />
      <rect x="70" y="18" width="12" height="8" rx="2" fill="#17304c" />
      <rect x="22" y="54" width="8" height="18" rx="3" fill="#c5d0da" />
      <rect x="40" y="54" width="8" height="18" rx="3" fill="#c5d0da" />
      <rect x="70" y="54" width="8" height="18" rx="3" fill="#c5d0da" />
      <rect x="86" y="54" width="8" height="18" rx="3" fill="#c5d0da" />
    </svg>
  );
}

export function DroneMark({ className = "h-14 w-20" }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 70" className={className} aria-hidden>
      <rect x="46" y="28" width="28" height="16" rx="4" fill="#243044" />
      <circle cx="24" cy="22" r="10" fill="none" stroke="#243044" strokeWidth="3" />
      <circle cx="96" cy="22" r="10" fill="none" stroke="#243044" strokeWidth="3" />
      <circle cx="24" cy="50" r="10" fill="none" stroke="#243044" strokeWidth="3" />
      <circle cx="96" cy="50" r="10" fill="none" stroke="#243044" strokeWidth="3" />
      <path d="M34 26 L48 34 M86 34 L72 26 M34 46 L48 40 M86 40 L72 46" stroke="#243044" strokeWidth="3" />
    </svg>
  );
}

export function PiMark({ className = "h-14 w-20" }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 80" className={className} aria-hidden>
      <rect x="18" y="16" width="84" height="52" rx="6" fill="#2f8f4e" />
      <rect x="28" y="26" width="28" height="20" rx="2" fill="#1e293b" />
      <circle cx="78" cy="34" r="6" fill="#d7dde6" />
      <rect x="70" y="46" width="22" height="8" rx="2" fill="#c5a15a" />
    </svg>
  );
}

export function XaiMark({ className = "h-12 w-12" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <rect width="48" height="48" rx="10" fill="#111B2C" />
      <path d="M14 14 L34 34 M34 14 L14 34" stroke="white" strokeWidth="3" />
    </svg>
  );
}
