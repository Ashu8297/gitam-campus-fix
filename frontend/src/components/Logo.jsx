// Original Campus Fix mark: a campus building with a check mark in the doorway.
export default function Logo({ size = 72, animate = true }) {
  return (
    <svg
      className={animate ? "logo logo-animate" : "logo"}
      width={size}
      height={size}
      viewBox="0 0 96 96"
      role="img"
      aria-label="Campus Fix logo"
    >
      <circle cx="48" cy="48" r="44" fill="var(--navy)" />
      {/* roof */}
      <path className="logo-roof" d="M22 40 L48 22 L74 40 Z" fill="var(--teal)" />
      {/* columns */}
      <g className="logo-body" fill="#fff">
        <rect x="26" y="43" width="8" height="26" rx="1.5" />
        <rect x="62" y="43" width="8" height="26" rx="1.5" />
        <rect x="22" y="69" width="52" height="5" rx="1.5" />
      </g>
      {/* check mark */}
      <path
        className="logo-check"
        d="M38 54 L45 61 L58 46"
        fill="none"
        stroke="var(--teal)"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
