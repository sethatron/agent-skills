# GitLab API Reference Notes

## Pagination

GitLab REST API defaults to 20 results per page, caps at 100.
Always use `per_page=100` and follow `X-Next-Page` headers.

Response headers:
- `X-Page`: current page number
- `X-Next-Page`: next page number (empty if last page)
- `X-Per-Page`: items per page
- `X-Total`: total items
- `X-Total-Pages`: total pages

Partial result sets are a critical failure mode — always accumulate all pages.

## Rate Limits

GitLab.com: 2000 requests/min for authenticated users.
Response header `RateLimit-Remaining` indicates remaining quota.
On 429: respect `Retry-After` header, use exponential backoff.

## Key Endpoints

### MR List
```
GET /api/v4/merge_requests?author_username=<user>&state=opened&per_page=100
```

### MR Detail
```
GET /api/v4/projects/:id/merge_requests/:iid
```

### MR Diffs
```
GET /api/v4/projects/:id/merge_requests/:iid/diffs?per_page=100
```

### MR Discussions (Comments)
```
GET /api/v4/projects/:id/merge_requests/:iid/discussions?per_page=100
```

### MR Approvals
```
GET /api/v4/projects/:id/merge_requests/:iid/approvals
```

### Token Self-Check
```
GET /api/v4/personal_access_tokens/self
```

### Project Issue
```
GET /api/v4/projects/:id/issues/:iid
```

## Token Scopes

Required minimum: `read_api`, `read_repository`

The skill validates scopes at startup via `/personal_access_tokens/self`.
Result is cached in memory for the duration of the invocation.

## Project ID Encoding

Project paths must be URL-encoded for API calls:
```
abacusinsights/abacus-v2/next-gen-platform/ng-data-pipeline
→ abacusinsights%2Fabacus-v2%2Fnext-gen-platform%2Fng-data-pipeline
```

Use `urllib.parse.quote(path, safe="")`.
