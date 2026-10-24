import { CALENDLY_URL, icsHref } from "@/lib/ics";
import styles from "./chat.module.css";

// After a qualified interview: the booked slot with "add to calendar", or the Calendly
// fallback when no slot fitted. Same in chat and voice.
export default function Booking({ interviewAt, uid }: { interviewAt: string | null; uid: string }) {
  if (!interviewAt)
    return (
      <p className={styles.booking}>
        ¿Ningún hueco te encajaba? <a href={CALENDLY_URL} target="_blank" rel="noreferrer">Elige otra hora</a>
      </p>
    );
  const when = new Date(interviewAt).toLocaleString("es-ES", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
  return (
    <p className={styles.booking}>
      Entrevista: <strong>{when}</strong> ·{" "}
      <a href={icsHref(interviewAt, uid)} download="entrevista-grupo-sazon.ics">Añadir a mi calendario</a>
    </p>
  );
}
