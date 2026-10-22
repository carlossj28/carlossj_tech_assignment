import styles from "./aurora.module.css";

// Decorative light behind the content: drifting aurora, a glowing horizon and film grain.
// "page" fills the viewport, "quiet" is a dimmer page backdrop, "panel" fills its parent.
export default function Aurora({ variant = "page" }: { variant?: "page" | "quiet" | "panel" }) {
  return (
    <div className={`${styles.aurora} ${styles[variant]}`} aria-hidden>
      <span className={`${styles.blob} ${styles.violet}`} />
      <span className={`${styles.blob} ${styles.coral}`} />
      <span className={`${styles.blob} ${styles.cobalt}`} />
      {variant !== "quiet" && (
        <>
          <span className={styles.glow} />
          <span className={styles.horizon} />
        </>
      )}
      <span className={styles.grain} />
    </div>
  );
}
