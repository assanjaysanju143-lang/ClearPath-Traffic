import { useState } from 'react'
import styles from './RouteCard.module.css'

const COLOR_MAP = {
  green: { bar: '#17803d', bg: '#17803d11', label: '#17803d' },
  amber: { bar: '#b45309', bg: '#b4530911', label: '#b45309' },
  red:   { bar: '#c0292a', bg: '#c0292a11', label: '#c0292a' },
}

export default function RouteCard({ route, index, selected, onClick }) {
  const [expanded, setExpanded] = useState(false)
  const colors = COLOR_MAP[route.traffic_color] || COLOR_MAP.green
  const pct = Math.round(route.traffic_ratio * 100)

  return (
    <div
      className={`${styles.card} ${selected ? styles.selected : ''}`}
      style={selected ? { borderColor: colors.bar, background: colors.bg } : {}}
      onClick={onClick}
    >
      <div className={styles.top}>
        <div className={styles.left}>
          <span className={styles.index}>{String(index + 1).padStart(2, '0')}</span>
          <div>
            <div className={styles.label}>{route.label}</div>
            <div className={styles.meta}>
              <span>{route.eta_minutes} min</span>
              <span className={styles.dot} />
              <span>{route.distance_km} km</span>
              {route.traffic_delay_minutes > 0 && (
                <>
                  <span className={styles.dot} />
                  <span style={{ color: colors.label }}>+{route.traffic_delay_minutes}m delay</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className={styles.right}>
          <span
            className={styles.badge}
            style={{ color: colors.label, borderColor: colors.bar + '55', background: colors.bg }}
          >
            {route.congestion_level}
          </span>
          {index === 0 && <span className={styles.bestBadge}>BEST</span>}
        </div>
      </div>

      {/* Traffic bar */}
      <div className={styles.barWrap}>
        <div className={styles.barBg}>
          <div
            className={styles.barFill}
            style={{ width: `${pct}%`, background: colors.bar }}
          />
        </div>
        <span className={styles.pct} style={{ color: colors.label }}>{pct}%</span>
      </div>

      {/* Turn by turn */}
      {route.steps && route.steps.length > 0 && (
        <button
          className={styles.toggle}
          onClick={e => { e.stopPropagation(); setExpanded(v => !v) }}
        >
          {expanded ? '↑ Hide directions' : '↓ Show turn-by-turn'}
        </button>
      )}

      {expanded && route.steps && (
        <div className={styles.steps}>
          {route.steps.map((step, i) => (
            <div key={i} className={styles.step}>
              <span className={styles.stepNum}>{i + 1}</span>
              <span className={styles.stepText}>{step.instruction}</span>
              {step.distance_m > 0 && (
                <span className={styles.stepDist}>{(step.distance_m / 1000).toFixed(1)}km</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
