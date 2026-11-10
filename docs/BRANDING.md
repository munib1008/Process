# dormakaba Branding

The tool and every exported document follow the dormakaba corporate identity as used in the
*Marketing Collateral 2017 – MEA Catalogues and Brochures Policy* (colours sampled from that PDF).

| Element | Value | Used for |
|---|---|---|
| dormakaba blue | `#003594` | Titles, headings, cover panel, table headers, primary buttons, swimlanes |
| dormakaba red | `#E4002B` | Kicker line above titles, emphasis, decision diamonds, *UNCONTROLLED DRAFT* marks |
| Light grey | `#E6E6E6` | Title band on covers, label cells in tables |
| Typeface | Arial | UI, Word and HTML exports. PDF embeds Arial on Windows, otherwise the metric-compatible Liberation Sans (Vera as last resort) |

## Layout rules applied
* **Cover** (DOCX / PDF / HTML): blue panel with white details and the *Classification* line; red title on the grey band; logo bottom right.
* **Pages**: red kicker line (document / department) above a blue title, as in the collateral slides.
* **Footer**: page number · document title · classification · *Region MEA* · logo.
* **Flow Studio templates**: white boxes with blue outline, red decision diamonds with white text, green-ringed start, black-ringed end, blue lanes — the same style as the supplied BMS diagrams.

## Settings
Administration → Settings: *Organisation name*, *Classification label* (default `Internal`), *Region label* (default `Region MEA`), *Export footer text*.

## Logo files
`mea_hub/static/brand/` – `dormakaba_logo.png` (colour, transparent), `dormakaba_logo_white.png` (for blue backgrounds),
`dormakaba_mark.png`, `favicon.png`. They were cut from the vector logo on the policy cover at 900 dpi.
Use them only for internal dormakaba material; follow Group Communication's brand guidelines for anything external.
