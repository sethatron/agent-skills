# API Reference

## Credential Loading

All API calls require credentials from `~/.jira_creds.env`:

```bash
source ~/.jira_creds.env
# Provides: ATLASSIAN_API_KEY, ATLASSIAN_USERNAME, GITLAB_TOKEN
```

## Jira Service Desk API — Create CMD Ticket

**Endpoint:** `POST https://abacusinsights.atlassian.net/rest/servicedeskapi/request`

**Auth:** Basic auth — `Authorization: Basic $(echo -n "$ATLASSIAN_USERNAME:$ATLASSIAN_API_KEY" | base64)`

**Service Desk ID:** 7
**Request Type ID:** 59 (Engineering Change Request with Approvals)

### Required Fields

```json
{
  "serviceDeskId": "7",
  "requestTypeId": "59",
  "requestFieldValues": {
    "summary": "NextGen 26.2.29 Release",
    "description": "<ADF JSON — see output-templates.md>",
    "customfield_10461": "DSP-7707, XFORM-1817, DSP-7471",
    "customfield_10229": "Revert the release branch merge to master for each affected project.",
    "customfield_10007": {"id": "10014"},
    "customfield_10416": "Regression testing captured in NGQA-3888",
    "customfield_10005": {"id": "10004"},
    "customfield_10006": {"id": "10010"}
  }
}
```

### Field Reference

| Field | Custom Field | Description |
|---|---|---|
| summary | — | CMD title (see naming conventions) |
| description | — | ADF JSON body with release details |
| Ticket Reference | customfield_10461 | Comma-separated Jira ticket IDs |
| Rollback Plan | customfield_10229 | Always: "Revert the release branch merge to master for each affected project." |
| Change Reason | customfield_10007 | Fixed value: `{"id": "10014"}` |
| Test Plan | customfield_10416 | NGQA reference or "Regression testing completed." |
| Request Participants | customfield_10005 | Fixed value: `{"id": "10004"}` |
| Organization | customfield_10006 | Fixed value: `{"id": "10010"}` |

### Response

```json
{
  "issueId": "12345",
  "issueKey": "CMD-2201",
  "requestTypeId": "59",
  ...
}
```

**Browse URL:** `https://abacusinsights.atlassian.net/browse/CMD-{key}`
**Portal URL:** `https://abacusinsights.atlassian.net/servicedesk/customer/portal/7/CMD-{key}`

### curl Example

```bash
source ~/.jira_creds.env
AUTH=$(echo -n "$ATLASSIAN_USERNAME:$ATLASSIAN_API_KEY" | base64)

curl -s -X POST \
  -H "Authorization: Basic $AUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "serviceDeskId": "7",
    "requestTypeId": "59",
    "requestFieldValues": {
      "summary": "NextGen 26.2.29 Release",
      "description": {"type": "doc", "version": 1, "content": [...]},
      "customfield_10461": "DSP-7707, XFORM-1817",
      "customfield_10229": "Revert the release branch merge to master for each affected project.",
      "customfield_10007": {"id": "10014"},
      "customfield_10416": "Regression testing captured in NGQA-3900",
      "customfield_10005": {"id": "10004"},
      "customfield_10006": {"id": "10010"}
    }
  }' \
  "https://abacusinsights.atlassian.net/rest/servicedeskapi/request"
```

## Jira REST API — Get Issue Summary

**Endpoint:** `GET https://abacusinsights.atlassian.net/rest/api/3/issue/{ticket}?fields=summary`

```bash
source ~/.jira_creds.env
AUTH=$(echo -n "$ATLASSIAN_USERNAME:$ATLASSIAN_API_KEY" | base64)
curl -s -H "Authorization: Basic $AUTH" \
  "https://abacusinsights.atlassian.net/rest/api/3/issue/DSP-7707?fields=summary"
```

## GitLab API — Create Merge Request

**Endpoint:** `POST https://gitlab.com/api/v4/projects/{encoded_path}/merge_requests`

**Auth:** Header — `PRIVATE-TOKEN: $GITLAB_TOKEN`

**Project path encoding:** URL-encode the full path:
`abacusinsights/abacus-v2/next-gen-platform/ng-infrastructure`
→ `abacusinsights%2Fabacus-v2%2Fnext-gen-platform%2Fng-infrastructure`

### Payload

```json
{
  "source_branch": "release-26.2.6",
  "target_branch": "master",
  "title": "[CMD-2201] NextGen 26.2.29 Release",
  "description": "This change releases..."
}
```

### Pre-Release MR (Phase 2 compound)

```json
{
  "source_branch": "CMD-2201",
  "target_branch": "qa",
  "title": "[CMD-2201] AIR 2.0.18 Pre-Release",
  "description": "...",
  "merge_when_pipeline_succeeds": true
}
```

### curl Example

```bash
source ~/.jira_creds.env
PROJECT="abacusinsights%2Fabacus-v2%2Fnext-gen-platform%2Fng-infrastructure"

curl -s -X POST \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_branch": "release-26.2.6",
    "target_branch": "master",
    "title": "[CMD-2201] NextGen 26.2.29 Release",
    "description": "This change releases NextGen 26.2.29..."
  }' \
  "https://gitlab.com/api/v4/projects/$PROJECT/merge_requests"
```

## GitLab API — Check Existing MR

Before creating, check if an MR already exists:

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$PROJECT/merge_requests?source_branch=release-26.2.6&state=opened"
```

If result array has entries, UPDATE the existing MR instead:

```bash
curl -s -X PUT \
  -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "...", "description": "..."}' \
  "https://gitlab.com/api/v4/projects/$PROJECT/merge_requests/{iid}"
```

## GitLab API — Check MR Merge State

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/$PROJECT/merge_requests/{iid}"
```

Check `"state": "merged"` and `"merge_commit_sha"` for cherry-pick operations.

## GitLab API — Search Breaking MRs

**Endpoint:** `GET https://gitlab.com/api/v4/groups/13931987/merge_requests`

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/groups/13931987/merge_requests?scope=all&labels=breaking&search=DSP-7707&in=title"
```

**Group ID:** 13931987 (abacusinsights/abacus-v2/next-gen-platform)

If the response is a non-empty array, the ticket has a breaking change.

## Error Handling

| Status | Action |
|---|---|
| 200-201 | Success — parse response |
| 401 | Auth failure — check credentials |
| 403 | Permission denied — check token scopes |
| 404 | Not found — verify paths/IDs |
| 429 | Rate limited — retry with exponential backoff |
| 5xx | Server error — retry once, then report |
