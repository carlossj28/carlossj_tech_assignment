import type { Status } from "@/lib/api";
import { STATUS } from "@/lib/labels";
import styles from "@/app/recruiter/recruiter.module.css";

export default function StatusPill({ status }: { status: Status }) {
  return <span className={`${styles.status} ${styles[status]}`}>{STATUS[status]}</span>;
}
