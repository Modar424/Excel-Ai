export default function Logo({ className = 'h-10 w-10' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <defs><linearGradient id="la" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#8fb0ff" /><stop offset="1" stopColor="#6558D9" /></linearGradient></defs>
      <path d="M20 3 36 11 20 19 4 11z" fill="#dfe8ff" /><path d="M4 17l16 8 16-8" fill="none" stroke="url(#la)" strokeWidth="4" strokeLinejoin="round" />
      <path d="M4 25l16 8 16-8" fill="none" stroke="#315BE8" strokeWidth="4" strokeLinejoin="round" />
    </svg>
  )
}
export function SheetIcon({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden="true">
      <defs><linearGradient id="sg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2fb36a" /><stop offset="1" stopColor="#0f7a45" /></linearGradient></defs>
      <rect x="3" y="3" width="34" height="34" rx="8" fill="url(#sg)" />
      <path d="M11 12h18M11 20h18M11 28h18M17 12v16M24 12v16" stroke="#fff" strokeOpacity=".85" strokeWidth="2" />
    </svg>
  )
}
