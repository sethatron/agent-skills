# Output Templates

## CMD Ticket Description (ADF Format)

The CMD description MUST be valid Atlassian Document Format (ADF) JSON. Plain text will be rejected.

### ADF Structure

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "paragraph",
      "content": [{"type": "text", "text": "This change releases NextGen 26.2.29 to customers, including:"}]
    },
    {
      "type": "bulletList",
      "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "ng-infrastructure @ 26.2.6"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "mdp-gateway @ 26.2.1"}]}]}
      ]
    },
    {
      "type": "table",
      "attrs": {"isNumberColumnEnabled": false, "layout": "default"},
      "content": [
        {
          "type": "tableRow",
          "content": [
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Ticket"}]}]},
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Summary Notes"}]}]},
            {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Breaking?"}]}]}
          ]
        },
        {
          "type": "tableRow",
          "content": [
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "DSP-7707", "marks": [{"type": "link", "attrs": {"href": "https://abacusinsights.atlassian.net/browse/DSP-7707"}}]}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Fix something"}]}]},
            {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "No"}]}]}
          ]
        }
      ]
    }
  ]
}
```

### ADF Node Types Used

- `paragraph` — text block
- `bulletList` + `listItem` — project list
- `table` + `tableRow` + `tableHeader`/`tableCell` — ticket table
- `text` — text node, optionally with `marks` for links

### ADF Link Format

```json
{
  "type": "text",
  "text": "DSP-7707",
  "marks": [{"type": "link", "attrs": {"href": "https://abacusinsights.atlassian.net/browse/DSP-7707"}}]
}
```

## Per-Project MR Description (Markdown)

Each project MR contains ONLY the tickets found in THAT project:

```markdown
This change releases NextGen 26.2.29 to customers, including:

| Ticket | Summary Notes | Breaking? |
| --- | --- | --- |
| [XFORM-1817](https://abacusinsights.atlassian.net/browse/XFORM-1817) | Fix predictive optimization in all workspaces | No |
| [DSP-7707](https://abacusinsights.atlassian.net/browse/DSP-7707) | Handle edge case in deployment | No |
```

For AIR/ONYX releases, replace "NextGen 26.2.29" with "AIR 2.0.18" / "ONYX 1.0.0" as appropriate.

## Config MR Description (Markdown)

The ng-deployment-config-files MR uses the AGGREGATED ticket table (all tickets from all projects):

```markdown
This change releases NextGen 26.2.29 to customers, including:

* ng-infrastructure @ 26.2.6
* mdp-gateway @ 26.2.1
* ng-air-continuous-deployment @ 26.2.3

| Ticket | Summary Notes | Breaking? |
| --- | --- | --- |
| [DSP-7707](https://abacusinsights.atlassian.net/browse/DSP-7707) | Fix something | No |
| [XFORM-1817](https://abacusinsights.atlassian.net/browse/XFORM-1817) | Fix another thing | No |
```

## Slack Notification — Platform Release

```
I have created a [change ticket](https://abacusinsights.atlassian.net/browse/CMD-{num}) and merge requests for the NextGen {version} release:
* [ng-deployment-config-files](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-deployment-config-files/-/merge_requests/{iid})
* [{project}](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/{project}/-/merge_requests/{iid})
* ...

The contents of this release are:
* [{ticket}](https://abacusinsights.atlassian.net/browse/{ticket}) | {summary}
* ...
```

## Slack Notification — AIR-Only Release

```
I have created a [change ticket](https://abacusinsights.atlassian.net/browse/CMD-{num}) and [merge request](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-abacus-insights-runtime/-/merge_requests/{iid}) for the AIR {version} release.

The contents of this release are:

[{ticket}](https://abacusinsights.atlassian.net/browse/{ticket}): {summary}
* ...
```

## Slack Notification — ONYX-Only Release

Same as AIR-only but with "ONYX" and `ng-onyx-runtime`.

## Slack Notification — AIR+ONYX Release

```
I have created a [change ticket](https://abacusinsights.atlassian.net/browse/CMD-{num}) and merge requests for the AIR {air_version} / ONYX {onyx_version} release:
* [ng-abacus-insights-runtime](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-abacus-insights-runtime/-/merge_requests/{iid})
* [ng-onyx-runtime](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-onyx-runtime/-/merge_requests/{iid})

The contents of this release are:
* [{ticket}](https://abacusinsights.atlassian.net/browse/{ticket}) | {summary}
* ...
```

## Slack Notification — Compound Phase 1 (AIR/ONYX)

Same as AIR/ONYX format above. Followed by PAUSE_1 message.

## Slack Notification — Compound Phase 2 (Pre-Release to QA)

```
I have created the AIR Pre-Release MRs to the `qa` branch:
* [{project}](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/{project}/-/merge_requests/{iid})
* ...

After the above MRs have been merged, I will cherry-pick them into the release branches.
```

Use "AIR" or "ONYX" or "AIR/ONYX" based on which runtimes are being updated.

## Slack Notification — Compound Phase 3 (Platform)

Same as standard platform format above.

## Config Variance Report

```
ng-deployment-config-files config variance:
The following changes have been merged to the `qa` branch of `ng-deployment-config-files` but were not specified in the original release notification:
* [JIRA-XYZ](https://abacusinsights.atlassian.net/browse/JIRA-XYZ) "Description" - [Merge Request](https://gitlab.com/abacusinsights/abacus-v2/next-gen-platform/ng-deployment-config-files/-/merge_requests/{iid})
```

## Merge Conflict Report

```
=== Merge Conflict Report ===
* ng-infrastructure: Clean
* ng-air-continuous-deployment: Clean
* mdp-gateway: CONFLICT — globals.tf (simple, auto-resolvable)
* ng-governance-infrastructure: Clean
```

## Compound Release PAUSE Messages

### PAUSE_1

```
=== PHASE 1/3 COMPLETE: AIR/ONYX Release ===
CMD: CMD-{num} — {title}
MR(s): {links}

The AIR/ONYX Slack notification has been output above. Copy it to Slack, and then let me know when the MR has been merged.

Then, I will create the required MRs to update the AIR/ONYX versions in the following projects via `CMD-{num}` → `qa`:
* {list the projects identified for AIR/ONYX policy updates from the Slack message}
```

### PAUSE_2

```
=== PHASE 2/3 COMPLETE: AIR/ONYX Pre-Release to QA ===
CMD: CMD-{num} — {title}
MR(s): {links}

The AIR/ONYX Pre-Release to QA Slack notification has been output above. Copy it to Slack, and then let me know when the MRs have been merged.

Then I will cherry-pick the commits into the release branches for the following projects:
* {list the projects}
```
