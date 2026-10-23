import type { Status } from "@/lib/api";
import { type Analytics as Data, type Day, analyze } from "@/lib/analytics";
import { KNOCKOUT, STATUS } from "@/lib/labels";
import type { ConversationRow } from "@/lib/recruiter";
import styles from "./analytics.module.css";
import panel from "./recruiter.module.css";

// Stack order, bottom to top: the outcome the recruiter wants to see grow sits on the baseline.
const STACK: Status[] = ["qualified", "pending", "disqualified"];

const DAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", day: "numeric", month: "short" });

export default function Analytics({ rows }: { rows: ConversationRow[] }) {
  const data = analyze(rows);
  const { started, completed, qualified } = data.funnel;

  return (
    <section className={styles.analytics} aria-labelledby="analytics-title">
      <span id="analytics-title" className={panel.kicker}>Analítica</span>

      <div className={`${styles.card} ${styles.wide}`}>
        <div className={styles.head}>
          <h2>Candidaturas por día</h2>
          <p className={styles.legend}>
            {STACK.map((s) => (
              <span key={s}>
                <i className={`${styles.swatch} ${panel[s]}`} aria-hidden />
                {STATUS[s]}
              </span>
            ))}
          </p>
        </div>
        <Daily days={data.daily} />
      </div>

      <div className={styles.card}>
        <h2>Embudo</h2>
        <Bar label="Iniciadas" value={started} max={started} tone="violet" />
        <Bar label="Completadas" value={completed} max={started} tone="sky" />
        <Bar label="Cualificadas" value={qualified} max={started} tone="mint" />
      </div>

      <div className={styles.card}>
        <h2>Por ciudad</h2>
        {data.cities.length ? (
          data.cities.map((c) => (
            <Bar key={c.city} label={c.city} value={c.total} max={data.cities[0].total} tone="violet"
              note={`${c.qualified} cualificada${c.qualified === 1 ? "" : "s"}`} />
          ))
        ) : (
          <p className={styles.none}>Aún no hay ciudades registradas.</p>
        )}
      </div>

      <div className={styles.card}>
        <h2>Motivos de descarte</h2>
        <Knockouts data={data} />
      </div>

      <div className={styles.card}>
        <h2>Canal y duración</h2>
        <Bar label="Chat" value={data.channels.chat} max={started} tone="violet" />
        <Bar label="Voz" value={data.channels.voice} max={started} tone="coral" />
        <p className={styles.figure}>
          <strong>{data.avgMinutes ?? "—"}</strong>
          {data.avgMinutes !== null && <small> min</small>}
          <span>de media hasta el cierre</span>
        </p>
      </div>
    </section>
  );
}

function Knockouts({ data }: { data: Data }) {
  const { no_license, out_of_service_area } = data.knockouts;
  const max = no_license + out_of_service_area; // each reason as a share of all knock-outs
  if (!max) return <p className={styles.none}>Ningún candidato descartado todavía.</p>;
  return (
    <>
      <Bar label={KNOCKOUT.no_license} value={no_license} max={max} tone="rose" />
      <Bar label={KNOCKOUT.out_of_service_area} value={out_of_service_area} max={max} tone="rose" />
    </>
  );
}

// Horizontal bar: label, value and share of `max` (the share is the bar's length).
function Bar({ label, value, max, tone, note }: { label: string; value: number; max: number; tone: string; note?: string }) {
  const share = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className={styles.bar} data-tone={tone}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>
        {value}
        <small>{note ?? `${share}%`}</small>
      </span>
      <span className={styles.track} aria-hidden>
        <span style={{ width: `${share}%` }} />
      </span>
    </div>
  );
}

// One stacked column per day; hover or focus a column for its numbers.
function Daily({ days }: { days: Day[] }) {
  const total = (d: Day) => STACK.reduce((sum, s) => sum + d[s], 0);
  const max = Math.max(1, ...days.map(total));

  return (
    <div className={styles.chart}>
      <span className={styles.max} aria-hidden>{max}</span>
      <ol className={styles.columns}>
        {days.map((d, i) => {
          const date = DAY.format(new Date(`${d.date}T12:00:00`));
          const parts = STACK.map((s) => `${d[s]} ${STATUS[s].toLowerCase()}`).join(", ");
          return (
            <li key={d.date} className={styles.day} tabIndex={0} aria-label={`${date}: ${parts}`}
              data-edge={i < 3 ? "start" : i > days.length - 4 ? "end" : undefined}>
              <span className={styles.stack} style={{ height: `${(total(d) / max) * 100}%` }} aria-hidden>
                {STACK.map((s) => d[s] > 0 && <span key={s} className={panel[s]} style={{ flexGrow: d[s] }} />)}
              </span>
              <span className={styles.tick} aria-hidden>{Number(d.date.slice(8))}</span>
              <span className={styles.tip} aria-hidden>
                <b>{date}</b>
                {STACK.map((s) => (
                  <span key={s}>
                    <i className={`${styles.swatch} ${panel[s]}`} />
                    {STATUS[s]} <em>{d[s]}</em>
                  </span>
                ))}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
