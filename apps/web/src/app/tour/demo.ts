import { api } from '@/lib/api'
import { useCampaigns } from '@/lib/campaign'
import { queryClient } from '@/lib/queryClient'
import { flyMission, useFlightRuns } from '@/sections/flight/run'
import { useFailuresAsked } from '@/sections/recovery/failuresAsked'
import { useMissionStore } from '@/stores/mission'
import { useTour } from '@/stores/tour'

/** The tour's own Calisto (simcore.examples.TOUR_MISSION_ID): never one of the team's missions. */
export const TOUR_MISSION_ID = '01JCALISTOTOUR000000000000'

/**
 * Opens the tour's Calisto and sets it working, so every section the tour visits
 * shows real numbers: the single flight (waited for), then a small Monte Carlo
 * campaign and the recovery failures (left running in the background).
 *
 * Unsaved changes to another mission are never thrown away: the tour stops at
 * `conflict` and asks first.
 */
export async function startDemo({ force = false } = {}) {
  const tour = useTour.getState()
  const { draft, isDirty } = useMissionStore.getState()
  if (draft && draft.meta.id !== TOUR_MISSION_ID && isDirty && !force) {
    tour.setDemo('conflict')
    return
  }
  try {
    tour.setDemo('loading')
    const doc = await api.tourMission()
    await queryClient.invalidateQueries({ queryKey: ['missions'] })
    if (!useTour.getState().active) return
    useMissionStore.getState().load(doc.mission)
    const mission = useMissionStore.getState().draft!

    tour.setDemo('flying')
    const flown = await flyMission(mission, false)
    useFlightRuns.getState().record(mission, flown.run)
    // These run as jobs; their sections poll them, so the tour doesn't wait.
    const campaign = await api.runMonteCarlo(mission)
    useCampaigns.getState().record(mission, campaign.id, null)
    useFailuresAsked.getState().ask(mission.meta.id!)
    if (useTour.getState().active) tour.setDemo('ready')
  } catch (e) {
    tour.setDemo('failed', e instanceof Error ? e.message : String(e))
  }
}
