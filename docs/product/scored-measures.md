# Standard scored measures

## Scope and sources

PHQ-9 and GAD-7 are fixed, versioned English adult screening questionnaires. They support symptom monitoring and clinician review; this implementation does not diagnose, recommend treatment or estimate suicide risk.

Published wording, choices, attribution and reproduction permission were checked against the original questionnaires hosted by CAMH:

- PHQ-9: https://www.camh.ca/-/media/files/phq-9_english-pdf.pdf
- GAD-7: https://www.camh.ca/-/media/files/gad-7_english-pdf.pdf

Both state that no permission is required to reproduce, translate, display or distribute. Attribution to Spitzer, Williams, Kroenke and colleagues and Pfizer's educational grant is retained. The application provides the original English version, not an improvised translation.

PHQ-9 score thresholds follow Kroenke et al. (2001), https://pubmed.ncbi.nlm.nih.gov/11556941/ (original paper https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/). GAD-7 thresholds follow the published instrument guidance and INSPQ's reference sheet: https://www.inspq.qc.ca/en/post-disaster-mental-health-impacts-surveillance-toolkit/standardized-measurement-instruments/information-sheets-standardized-measurement-instruments-recommended/anxiety-symptoms .

## Staff and patient workflow

1. Client forms → Add standard measure opens a side panel. Staff need intake-create and clinical-read permissions and acknowledge responsibility for selecting suitable adult clients and reviewing responses.
2. The practice-local library gains one version of the selected measure. Repeating the import is idempotent. It sends no email and creates no assignment. Standard wording and scoring cannot be edited through the template editor; availability can be changed.
3. Assign normally, or use the existing reviewed Share forms flow from a client record. Its email/privacy controls remain unchanged. Assignment snapshots include the exact standard questions and version code. Custom templates with similar names are never automatically scored.
4. The portal client answers the published questions. Partial drafts remain unscored. Final submission requires all scored items; the optional PHQ-9 functional difficulty item is recorded separately and excluded from the total. Stale submitted forms cannot be edited through the portal.
5. Authorized staff review the score and original responses. The client record's Measures tab shows separate PHQ-9 and GAD-7 time-series charts with exact dates/scores in accessible tables. It uses at most the latest 50 submitted standard assignments and displays the actual submission time, not an inferred assessment date. Clinical-read and intake-read permissions are both needed. Drafts, unknown versions, altered question snapshots and incomplete/invalid responses never receive estimated scores.

## Scoring and follow-up

Each scored answer contributes 0–3. PHQ-9 totals 0–27, with symptom ranges 0–4 Minimal, 5–9 Mild, 10–14 Moderate, 15–19 Moderately severe, 20–27 Severe. GAD-7 totals 0–21: 0–4 Minimal, 5–9 Mild, 10–14 Moderate, 15–21 Severe. The charts use separate full scales and actual elapsed time between submissions. They do not describe a drop as clinical recovery or a reliable-change threshold.

A nonzero PHQ-9 item 9 is highlighted independently of the total in the staff form queue, result and history. Staff must explicitly confirm reviewing that item and their follow-up responsibility before marking the form reviewed. Review records the existing authenticated reviewer/time. It does not document a completed risk assessment or risk resolution. An endorsed item remains visible after review. The portal states that forms are not continuously monitored and are not an urgent-help channel. There are no automatic emergency contacts, risk classifications, emails containing results or background surveillance promises.

Responses and versioned snapshots remain in the existing tenant-scoped intake records. Clinical/all practice exports include both source records and reproducible derived measure_results; billing-only exports exclude them. No external charting service or analytics receives clinical data.

## Release

Requires portal.0016_standard_measures via the normal migration/release workflow. No standard questionnaires are seeded across production practices; each practice explicitly adds the ones it uses. No existing response, assignment, signature or custom template is rewritten.
