import styles from "./brand.module.css";

// Grupo Sazón wordmark: a sun on the horizon (the aurora motif) plus the side of the product.
export default function Brand({ area }: { area: string }) {
  return (
    <span className={styles.brand}>
      <span className={styles.mark} aria-hidden />
      <span className={styles.name}>Grupo Sazón</span>
      <span className={`${styles.area} eyebrow`}>{area}</span>
    </span>
  );
}
