import type { ThrustCurveImport } from '@/lib/api'
import { useMissionStore } from '@/stores/mission'

/** Puts an imported motor in the mission, with its curve in the assets, dropping the old curve. */
export function useApplyMotor() {
  const edit = useMissionStore((s) => s.edit)
  return (imported: Pick<ThrustCurveImport, 'asset' | 'motor'>) =>
    edit((d) => {
      const old = d.motor?.thrust_curve
      const { sha256, filename, size } = imported.asset
      d.motor = imported.motor
      d.assets = { ...d.assets, [sha256]: { kind: 'thrust_curve', filename, size } }
      const drag = [d.rocket?.drag.power_off.table, d.rocket?.drag.power_on.table]
      if (old && old !== sha256 && !drag.includes(old) && d.assets) delete d.assets[old]
    })
}
