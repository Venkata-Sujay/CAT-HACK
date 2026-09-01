# Brand assets

## Caterpillar logo — drop it here

Save the official logo from the hackathon pack as **one** of these, exactly:

```
frontend/public/brand/cat-logo.svg     <- preferred
frontend/public/brand/cat-logo.png     <- also fine (use a transparent PNG, >= 200px wide)
```

Nothing else to do. `<CatBadge>` in `src/components/Brand.tsx` probes for the
SVG first, then the PNG, and falls back to a built wordmark if neither is
present — so the UI never shows a broken image, and the moment you add the file
it appears in the sidebar, on the login screen and in the page corner.

Reload the browser after adding the file (Vite serves `public/` statically and
does not hot-reload new files there).
