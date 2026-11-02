import {
  Activity,
  BookOpen,
  ChartColumn,
  ChartLine,
  Cpu,
  Crosshair,
  Flame,
  FolderOpen,
  GitCompare,
  ListChecks,
  MapPin,
  Rocket,
  Rotate3d,
  Settings,
  Umbrella,
  Weight,
  Wind,
  type LucideIcon,
} from 'lucide-react'
import type { ComponentType } from 'react'

export type RailGroup = 'setup' | 'analysis' | 'field' | 'hardware' | 'footer'

export const RAIL_GROUP_LABEL: Record<RailGroup, string> = {
  setup: 'Mission setup',
  analysis: 'Analysis',
  field: 'Field',
  hardware: 'Hardware',
  footer: '',
}

/** What every module in `src/sections/<id>/` exports. */
export interface SectionModule {
  Centre: ComponentType
  Pane?: ComponentType
}

export interface SectionDef {
  id: string
  label: string
  icon: LucideIcon
  group: RailGroup
  /** Whether the section docks a right-hand editing pane. */
  hasPane: boolean
  /** Tab names on a phone, where centre and pane are tabs. Default Overview and Settings. */
  centreLabel?: string
  paneLabel?: string
  /** Whether the section owns the paths below it (e.g. /docs/methods/flight). */
  subpaths?: boolean
  load: () => Promise<SectionModule>
}

export const SECTIONS: SectionDef[] = [
  { id: 'missions', label: 'Missions', icon: FolderOpen, group: 'setup', hasPane: true, centreLabel: 'List', paneLabel: 'Details', load: () => import('@/sections/missions') },
  { id: 'rocket', label: 'Rocket', icon: Rocket, group: 'setup', hasPane: true, paneLabel: 'Import', load: () => import('@/sections/rocket') },
  { id: 'motor', label: 'Motor', icon: Flame, group: 'setup', hasPane: true, paneLabel: 'Motor', load: () => import('@/sections/motor') },
  { id: 'recovery', label: 'Recovery', icon: Umbrella, group: 'setup', hasPane: true, load: () => import('@/sections/recovery') },
  { id: 'site', label: 'Site', icon: MapPin, group: 'setup', hasPane: true, centreLabel: 'Map', load: () => import('@/sections/site') },
  { id: 'weather', label: 'Weather', icon: Wind, group: 'setup', hasPane: true, load: () => import('@/sections/weather') },

  { id: 'flight', label: 'Single flight', icon: ChartLine, group: 'analysis', hasPane: true, paneLabel: 'Run', load: () => import('@/sections/flight') },
  { id: 'trajectory', label: 'Trajectory 3D', icon: Rotate3d, group: 'analysis', hasPane: true, paneLabel: 'Playback', load: () => import('@/sections/trajectory') },
  { id: 'dispersion', label: 'Dispersion', icon: Crosshair, group: 'analysis', hasPane: true, paneLabel: 'Campaign', load: () => import('@/sections/dispersion') },
  { id: 'results', label: 'Monte Carlo results', icon: ChartColumn, group: 'analysis', hasPane: true, paneLabel: 'All outputs', load: () => import('@/sections/results') },
  { id: 'ballast', label: 'Ballast', icon: Weight, group: 'analysis', hasPane: true, load: () => import('@/sections/ballast') },
  { id: 'compare', label: 'Compare', icon: GitCompare, group: 'analysis', hasPane: true, paneLabel: 'Runs', load: () => import('@/sections/compare') },
  { id: 'post-flight', label: 'Post-flight', icon: Activity, group: 'analysis', hasPane: true, paneLabel: 'Flight log', load: () => import('@/sections/post-flight') },

  { id: 'go-no-go', label: 'Go / no-go', icon: ListChecks, group: 'field', hasPane: true, centreLabel: 'Board', paneLabel: 'Rules', load: () => import('@/sections/go-no-go') },

  { id: 'hil', label: 'Hardware in the loop', icon: Cpu, group: 'hardware', hasPane: true, paneLabel: 'Session', load: () => import('@/sections/hil') },

  { id: 'docs', label: 'Docs', icon: BookOpen, group: 'footer', hasPane: true, centreLabel: 'Page', paneLabel: 'Contents', subpaths: true, load: () => import('@/sections/docs') },
  { id: 'settings', label: 'Settings', icon: Settings, group: 'footer', hasPane: false, load: () => import('@/sections/settings') },
]

export const SECTION_BY_ID = Object.fromEntries(SECTIONS.map((s) => [s.id, s])) as Record<string, SectionDef>
