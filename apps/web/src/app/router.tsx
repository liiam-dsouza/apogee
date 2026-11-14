import { createBrowserRouter, Navigate } from 'react-router'
import { Home } from './Home'
import { SectionError } from './SectionError'
import { SECTIONS } from './sections'
import { SectionView } from './SectionView'
import { Shell } from './Shell'

/** FIELD_MODE lands on the go/no-go board instead of the home screen. */
const FIELD_MODE = import.meta.env.VITE_FIELD_MODE === 'true'
const LANDING = FIELD_MODE ? '/go-no-go' : '/'

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: FIELD_MODE ? <Navigate to={LANDING} replace /> : <Home /> },
      // Keyed so each section gets its own panel group and persisted layout.
      ...SECTIONS.map((s) => ({
        path: s.subpaths ? `${s.id}/*` : s.id,
        element: <SectionView key={s.id} id={s.id} />,
        errorElement: <SectionError />,
      })),
      { path: '*', element: <Navigate to={LANDING} replace /> },
    ],
  },
])
