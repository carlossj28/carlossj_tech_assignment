import styles from "@/app/recruiter/recruiter.module.css";

const TONES = 7; // hues in recruiter.module.css (.tone0 … .tone6)

// BKDR string hash: unlike a sum of char codes, names with similar letters land on different tones.
function toneOf(name: string): number {
  let hash = 0;
  for (const c of name) hash = (Math.imul(hash, 131) + c.codePointAt(0)!) >>> 0;
  return hash % TONES;
}

// Candidate initials in an aurora ring; the colour comes from the name, so each person keeps theirs.
export default function Avatar({ name, size = 40 }: { name: string | null; size?: number }) {
  const initials = name
    ?.trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return (
    <span
      className={`${styles.avatar} ${name ? styles[`tone${toneOf(name)}`] : styles.anonymous}`}
      style={{ "--size": `${size}px` } as React.CSSProperties}
      aria-hidden
    >
      {initials || "?"}
    </span>
  );
}
