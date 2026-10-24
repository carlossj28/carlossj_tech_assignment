import styles from "./orb.module.css";

// Rita's avatar: a glowing orb whose light swirls and breathes while she is typing. `still` drops the outer glow.
export default function Orb({ size = 28, active = false, still = false }: { size?: number; active?: boolean; still?: boolean }) {
  return (
    <span
      className={`${styles.orb} ${active ? styles.active : ""} ${still ? styles.still : ""}`}
      style={{ "--size": `${size}px` } as React.CSSProperties}
      aria-hidden
    />
  );
}
