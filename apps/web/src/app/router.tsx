import { createBrowserRouter, Navigate } from 'react-router'
import { SectionError } from './SectionError'
import { SECTIONS } from './sections'
import { SectionView } from './SectionView'
import { Shell } from './Shell'

/** FIELD_MODE lands on the go/no-go board instead of the mission list. */
const LANDING = import.meta.env.VITE_FIELD_MODE === 'true' ? '/go-no-go' : '/missions'

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to={LANDING} replace /> },
      // Keyed so each section gets its own panel group and persisted layout.
      ...SECTIONS.map((s) => ({
        path: s.id,
        element: <SectionView key={s.id} id={s.id} />,
        errorElement: <SectionError />,
      })),
      { path: '*', element: <Navigate to={LANDING} replace /> },
    ],
  },
])
