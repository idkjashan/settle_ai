# Auto-Settle AI — frontend prototype

A responsive claims-desk website for the Auto-Settle AI hackathon concept. This is a real, interactive browser prototype built with semantic HTML, CSS, and vanilla JavaScript. All claim data, prices, assessments, and outcomes are illustrative local demo state. No backend, API routes, network claim submission, or persistent audit store is implemented.

## Run it

Serve the project root on port 3000, for example:

```bash
python3 -m http.server 3000 --bind 0.0.0.0
```

Open `/`. The WebDev route manifest is `public/manus-routes.json`.

## Screens and interaction map

The Overview contains a review queue and a preloaded sample claim. Claims opens the claim workstation. Its section tabs cover assessment, itemized repair economics, negotiation, audit, and the final decision. New claim opens the responsive upload form; image/video previews stay in the browser, and the camera action uses browser media access only after the user presses it. Guardrails lists the source escalation rules and includes a scenario selector for visualizing safe handoff states. Audit trail can be downloaded as JSON from client-side state or printed to PDF using the browser.

The settlement conversation starts at ₹7,500 from a ₹10,000 net eligible claim. It displays an ₹8,500 target and ₹9,500 maximum (75% / 85% / 95%), below the ₹25,000 autonomous net-repair ceiling. Counteroffers above ₹9,500 are blocked in the interface. A customer acceptance, garage choice, or human escalation produces a visible outcome state and adds a chronological demo audit entry. The offered numbers do not represent a live pricing engine.

## Visual system

The visual direction is calm, editorial product software rather than a generic AI dashboard: warm mineral-white surfaces, ink/navy text, restrained pine-green for allowed actions, amber for caution, and red only for a hard stop. A compact utility sans handles controls and dense claim data; an editorial serif is reserved for large page headings; a mono face is used for technical identifiers. Information is grouped by meaning, with open whitespace and hairline rules instead of gradients, glass panels, or repeated icon tiles. Status is written as text as well as encoded by color. Mobile reorganizes the claim into a single reading column and keeps the core destinations within reach.

Design references consulted:

- Apple Human Interface Guidelines, Typography: https://developer.apple.com/design/human-interface-guidelines/typography — readable sizes and weights, restrained typeface count, and hierarchy.
- Apple Human Interface Guidelines, Layout: https://developer.apple.com/design/human-interface-guidelines/layout — order content by importance, align related information, and use progressive disclosure.
- Apple Human Interface Guidelines, Accessibility: https://developer.apple.com/design/human-interface-guidelines/accessibility — contrast, perceivable states beyond color, and accessible descriptions.
- web.dev, Responsive web design basics: https://web.dev/articles/responsive-web-design-basics — adapt the layout to viewport size and interaction mode, rather than scaling a desktop canvas down.
- Adam Wathan, “Why Your AI Keeps Building the Same Purple Gradient Website”: https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website — a critique of common repetitive AI-produced visual patterns such as purple accents, centered hero blocks, and card grids.

## Files

- `index.html` — semantic page shell, desktop/mobile navigation, claim screens, dialogs, and labels.
- `src/styles.css` — responsive layout, component states, print styles, and visual tokens.
- `src/app.js` — client-side screen switching, sample claim interaction, camera capture, guardrail scenario preview, and local audit download.
- `assets/damage-evidence.svg` — original illustrative damage evidence artwork.

## Next implementation boundary

Replace the hard-coded sample claim and local event history with the product's approved data and services when the application is extended. Preserve the visible user journey and offer-boundary states. Keep any actual pricing, eligibility, fraud, policy, payment, and final-decision authority outside the browser UI; this prototype does not implement those systems.
