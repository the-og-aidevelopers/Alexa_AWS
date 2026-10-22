// The Pillow mark: a puffy pillow with a capsule resting on it.
export default function Logo({ size = 40, className = "" }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 128 128" role="img" aria-label="Pillow">
      <defs>
        <linearGradient id="pillow-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3a8a68" />
          <stop offset="1" stopColor="#15342a" />
        </linearGradient>
        <clipPath id="pillow-capsule"><rect x="38" y="52" width="52" height="25" rx="12.5" /></clipPath>
      </defs>
      <rect width="128" height="128" rx="30" fill="url(#pillow-bg)" />
      <path d="M18 36 Q64 20 110 36 Q121 64 110 92 Q64 108 18 92 Q7 64 18 36 Z" fill="#f2f7f4" />
      <path d="M27 42 Q64 31 101 42" fill="none" stroke="#c9ddd1" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M27 86 Q64 97 101 86" fill="none" stroke="#c9ddd1" strokeWidth="2.5" strokeLinecap="round" />
      <g transform="rotate(-30 64 64)">
        <rect x="38" y="52" width="52" height="25" rx="12.5" fill="#6cb590" />
        <rect x="38" y="52" width="26" height="25" fill="#2b6e51" clipPath="url(#pillow-capsule)" />
      </g>
    </svg>
  );
}
