import styles from './StatsBar.module.css'

export default function StatsBar({ data }) {
  if (!data) return null
  const best = data.routes?.[0]

  return (
    <div className={styles.bar}>
      <div className={styles.stat}>
        <span className={styles.label}>Best ETA</span>
        <span className={styles.val} style={{ color: '#17803d' }}>{best?.eta_minutes ?? '—'} min</span>
      </div>
      <div className={styles.divider} />
      <div className={styles.stat}>
        <span className={styles.label}>Distance</span>
        <span className={styles.val}>{best?.distance_km ?? '—'} km</span>
      </div>
      <div className={styles.divider} />
      <div className={styles.stat}>
        <span className={styles.label}>Delay saved</span>
        <span className={styles.val} style={{ color: '#17803d' }}>
          {data.routes?.length > 1
            ? `${data.routes[data.routes.length - 1].traffic_delay_minutes - (best?.traffic_delay_minutes ?? 0)} min`
            : '—'}
        </span>
      </div>
      <div className={styles.divider} />
      <div className={styles.stat}>
        <span className={styles.label}>Routes found</span>
        <span className={styles.val}>{data.routes?.length ?? 0}</span>
      </div>
    </div>
  )
}
