import styles from './RouteLoadBar.module.css'

const LEVEL_COLOR = { LOW: '#17803d', MODERATE: '#b45309', HIGH: '#c0292a' }

/**
 * RouteLoadBar — the visual heart of the "divide vehicles across routes"
 * idea. Each route gets a lane; each active user on that route is drawn as
 * a moving dot. Watching cars visibly redistribute themselves across lanes
 * as new users request routes IS the pitch, so it gets a dedicated widget
 * instead of being buried in a stats table.
 */
export default function RouteLoadBar({ routes, routeLoads }) {
  if (!routes || routes.length === 0 || !routeLoads || routeLoads.length === 0) return null

  const totalUsers = routeLoads.reduce((sum, l) => sum + l.active_users, 0) || 1

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.title}>Live route load</span>
        <span className={styles.subtitle}>{totalUsers} driver{totalUsers === 1 ? '' : 's'} currently routed</span>
      </div>

      {routeLoads.map((load) => {
        const route = routes.find(r => r.route_id === load.route_id)
        const color = LEVEL_COLOR[route?.congestion_level] || '#5a5550'
        const dots = Array.from({ length: load.active_users })

        return (
          <div key={load.route_id} className={styles.lane}>
            <div className={styles.laneLabel}>
              <span className={styles.laneName}>{load.label}</span>
              <span className={styles.laneCount} style={{ color }}>{load.active_users}</span>
            </div>
            <div className={styles.track} style={{ borderColor: color + '33' }}>
              <div className={styles.trackFill} style={{ background: color + '14' }} />
              {dots.map((_, i) => (
                <span
                  key={i}
                  className={styles.dot}
                  style={{
                    background: color,
                    left: `${6 + (i / Math.max(load.active_users, 6)) * 82}%`,
                    animationDelay: `${i * 0.15}s`,
                  }}
                />
              ))}
              {load.active_users === 0 && <span className={styles.emptyLabel}>open</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
