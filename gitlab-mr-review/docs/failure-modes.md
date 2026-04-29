# gitlab-mr-review Failure Modes


## Failure Handling

| Failure | Behavior |
|---------|----------|
| API unavailable | Use cache if available, clear error if not |
| Cache corrupted | Delete and re-fetch with operator confirmation |
| Clone fails | Document in review.md, continue with API data only |
| Rate limit | Exponential backoff, surface wait time |
