import styles from './IncidentsPanel.module.css'

const SEVERITY_COLOR = { MINOR: '#b45309', MODERATE: '#b45309', MAJOR: '#c0292a', CRITICAL: '#c0292a', UNKNOWN: '#5a5550' }
const TYPE_ICON = { ACCIDENT: '⚠', ROAD_CLOSURE: '✕', ROAD_WORKS: '⚙', CONGESTION: '↔', DEFAULT: '●' }

export default function IncidentsPanel({ incidents }) {
  if (!incidents || incidents.length === 0) return null

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span className={styles.title}>Live Incidents</span>
        <span className={styles.count}>{incidents.length}</span>
      </div>
      <div className={styles.list}>
        {incidents.map((inc, i) => (
          <div key={i} className={styles.item}>
            <span
              className={styles.icon}
              style={{ color: SEVERITY_COLOR[inc.severity] || '#5a5550' }}
            >
              {TYPE_ICON[inc.type] || TYPE_ICON.DEFAULT}
            </span>
            <div className={styles.info}>
              <span className={styles.type}>{inc.type.replace(/_/g, ' ')}</span>
              <span className={styles.desc}>{inc.description || 'No details'}</span>
            </div>
            {inc.delay_minutes > 0 && (
              <span className={styles.delay}>+{inc.delay_minutes}m</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
