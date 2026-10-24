import type { Status } from "@/lib/api";
import { STATUS } from "@/lib/labels";
import styles from "@/app/recruiter/recruiter.module.css";

// Glowing dot + label: the colour never carries the status on its own.
export default function StatusPill({ status }: { status: Status }) {
  return (
    <span className={`${styles.status} ${styles[status]}`}>
      <span className={styles.dot} aria-hidden />
      {STATUS[status]}
    </span>
  );
}
