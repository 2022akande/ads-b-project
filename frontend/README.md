# Frontend — ai-sysdef

Next.js (App Router) + TypeScript + Tailwind demo dashboard for the ADS-B
injection defense system. Implements TDD §6.

## Run

```bash
npm install
npm run dev      # http://localhost:3000
```

Requires the backend running on `http://127.0.0.1:8000` (see `../backend`).

- REST is proxied through Next via a rewrite (`next.config.mjs`), so the browser
  talks to one origin.
- The WebSocket connects directly to the backend at `ws://127.0.0.1:8000/ws/stream`.
  Override with `NEXT_PUBLIC_WS_URL` if the backend is elsewhere.

## Layout

```
app/
  page.tsx              # dashboard composition
  layout.tsx, globals.css
components/
  AirspaceMap.tsx       # offline SVG radar (equirectangular projection, no tiles)
  TrackList.tsx         # sortable track table
  TrackDetail.tsx       # selected-track kinematics + model reasoning
  AlertFeed.tsx         # chronological detections with reasons
  AttackInjector.tsx    # fire path/velocity/ghost attacks (demo centerpiece)
lib/
  useStream.ts          # WebSocket client hook → tracks / alerts / stats
  api.ts                # REST helpers (inject, clear, model info)
  types.ts              # shared types + airspace bounds (mirror the backend)
```

## Notes

- The map is a dependency-light **offline SVG** (no MapLibre/Leaflet tile server),
  so the demo runs with no internet. Swapping in a real basemap is a drop-in change
  to `AirspaceMap.tsx` (TDD §6.1).
- Legit tracks render green; malicious tracks pulse red with their attack type.
- `BOUNDS` in `lib/types.ts` must match the airspace box in
  `backend/app/generator.py`.
