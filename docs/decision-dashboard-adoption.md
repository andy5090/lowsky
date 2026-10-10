# Decision dashboard adoption

The local `LOW_SKY_decisiondashboard.docx` proposes a compact judgment card before confirmation. The source is retained locally and is not published. This implementation applies its interaction design to received-evidence review and explicitly scripted follow-ups.

| Proposal | Implemented behavior |
| --- | --- |
| Five questions before choosing | One selected received object: evidence and uncertainty, remaining review time, available review actions, waiting benefit/cost, and the local human decision maker. |
| Context-dependent actions | Observe, request a mock sensor review, raise review priority, or dismiss with a selected reason. Evidence needing review or a completed scripted follow-up also permits escalation, mock notice, recording review, and holding review. |
| Observe then reassess | Continue observing or request sensor review schedules one scripted visual-review receipt 30 simulation seconds later. The clock keeps running; 30 seconds are consumed from the review window. Pausing explicitly also pauses that schedule; playback speed applies. |
| Conditional choices | Choices close on stale observations, dismissal, or expiry. The server checks the current run/card version and enabled actions again when confirming. Duplicate submissions are rejected. |
| Minimal input | Choose an action and confirm; dismissal additionally requires a reason selection. Comment and reviewer alias are optional. Reasons are human opinions, never verified classifications. |
| Seven-field log | Event, received evidence, card assessment, uncertainty, decision/actor/outcome, reason, and simulation/wall time persist before success. Export `/api/dashboard/audit`; default journal `.local/dashboard-decisions.jsonl`. |
| Agent reassessment | The arrival of a scripted follow-up triggers the existing event assessment while playback continues. The agent sees labeled aggregate pending/received counts, without hidden coordinates, aliases or free text. |

## Meaning of the displayed states

`observed` means received evidence exists. `needs_review` means reports are incomplete, disagree or have different observation times. `corroborated` is displayed as **Follow-up received** and means a requested scripted review arrived; it is not verified identity or hostility. `stale` and `closed` disable confirmation. There is no combat readiness or engagement authorization state.

The per-object review deadline is first received observation + 90 simulation seconds, capped at scenario end. This is a configurable scene assumption (`REVIEW_WINDOW_MS`), not estimated flight arrival or an engagement window. It is separate from the existing event checkpoint's 30-second response window. Waiting cannot be scheduled when fewer than 30 seconds remain. One follow-up per object per run is supported. New runs, seek and reset clear active follow-ups while retaining journal records. Server restart creates a new run; old records do not reapply actions.

Mock notices stay inside the local journal and explicitly record `transmitted: false`. Priority, escalation, dismissal and hold are local review records. No sensors move, no institutional message is sent and no track is removed from the observation map by dismissal. The existing scripted movement/facility branch remains a separate explicit control.

## Content not adopted as operating rules

The example's percentages, aircraft-type inference from sound, military-target ETA, weapon ranking, firing/engagement buttons, resource allocation and real approval hierarchy are not implemented. No RF reception is not evidence of a fiber connection or of jamming effectiveness. Acoustic observations do not establish identity or intent. The interface leaves these unknown rather than supplying unsupported probabilities. The simulated visual-review receipt changes the review workflow only; it never becomes a fabricated sensor observation.

The journal is local append-only storage, not authenticated identity or tamper-proof remote storage. A 10,000-record limit bounds this journal; the UI displays the latest 20 records in the current run. Export includes every saved record.
