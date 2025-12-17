# Animated Diagrams

Open `backend/diagrams/animated/index.html` in your browser to see an animated version of the flow/sequence diagrams.

## Notes

- This HTML uses Mermaid via a CDN (`jsdelivr`). If you open it offline, it won’t render.
- If you want offline support, download a Mermaid build and change the import line in `index.html` to point to a local file.
- Animation is purely CSS (stroke dash animation on SVG paths). To slow it down, edit the `dashFlow` duration in `index.html`.

