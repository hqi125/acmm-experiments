# Provider rate and pacing policy sources

Checked: 2026-11-15

This package distinguishes provider-documented limits and recommendations from ACMM
operating margins. GitHub response headers and explicit provider recovery guidance remain
authoritative at runtime; ACMM static values are conservative admission defaults, not a
claim to reconstruct GitHub's undisclosed secondary-limit policy.

## Official references

- GitHub REST API rate limits:
  https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- GitHub REST API best practices:
  https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- GitHub repository limits:
  https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits

## REST/API policy

| ACMM setting | Value | Provider basis |
| --- | ---: | --- |
| `request_interval_seconds` | 1.0 s | ACMM conservative serial baseline. GitHub recommends serial requests to reduce secondary-rate pressure, but does not publish a fixed minimum interval for ordinary reads. |
| `mutation_interval_seconds` | 2.0 s | ACMM margin over GitHub's recommendation to wait at least 1 second between large numbers of `POST`, `PATCH`, `PUT`, or `DELETE` requests. |
| `content_requests_per_minute` | 60 | ACMM operating threshold below GitHub's general secondary limit of 80 content-generating requests/minute. |
| `content_requests_per_hour` | 360 | ACMM operating threshold below GitHub's general secondary limit of 500 content-generating requests/hour. |
| `secondary_backoff_seconds` | 60, 120, 240, 480, 960 s | GitHub says that, when no `Retry-After` or exhausted primary reset applies, wait at least 1 minute and then increase the wait exponentially if secondary limiting continues. The exact five-step sequence is ACMM policy. |
| `max_secondary_retries` | 5 | ACMM retry cap. GitHub recommends eventually throwing an error after a specific number of retries but does not prescribe the count. |
| `primary_remaining_floor` | 1000 | ACMM reserve, not a GitHub limit. GitHub App installation tokens have a minimum primary limit of 5000 requests/hour outside higher Enterprise/scaled cases; response `x-ratelimit-*` headers are authoritative. |
| `primary_reset_grace_seconds` | 3.0 s | ACMM clock/network safety margin, not provider-prescribed. |
| `retry_after_grace_seconds` | 3.0 s | ACMM clock/network safety margin added after provider `Retry-After`, not provider-prescribed. |

GitHub currently documents general secondary ceilings of 100 concurrent requests, 900 REST
points/minute, 2000 GraphQL points/minute, 90 seconds of CPU time per 60 seconds of real
time, and generally 80/500 content-generating requests per minute/hour. GitHub explicitly
notes that secondary limits may change without notice, so these values are cold-start
reference information rather than hard provider guarantees.

## Git transport policy

| ACMM setting | Value | Provider basis |
| --- | ---: | --- |
| `push_interval_seconds` | 12.0 s | GitHub recommends no more than 6 pushes/minute/repository, which implies at least 10 seconds between sustained pushes. ACMM uses 12 seconds. |
| `remote_read_interval_seconds` | 0.1 s | GitHub recommends no more than 15 Git read operations/second/repository, which implies at least 1/15 second between sustained reads. ACMM uses 0.1 seconds. |

## MCP fallback governor

The Experiment 2 package deploys the fork with `request_interval=1s` and
`mutation_interval=2s`. During an active Core Provider Gate these local proactive sleeps are
bypassed so Core is the single admission authority. Outside an active gate the MCP fork's
local governor remains a conservative fallback.

The fork's internal `500ms` request interval is an unconfigured fallback implementation
default, not a GitHub-documented number and not the value used by this package. Its 2-second
mutation interval is an ACMM margin over the documented 1-second recommendation. The
secondary fallback sequence starts at 60 seconds and doubles, matching the documented
minimum-one-minute-plus-exponential guidance while choosing ACMM-specific concrete steps.

## Recovery precedence

When GitHub returns rate-limit guidance, provider recommendations take precedence over local
heuristics:

1. honor `Retry-After` when present;
2. if `x-ratelimit-remaining` is zero, wait until `x-ratelimit-reset`;
3. otherwise treat a 403/429 secondary-limit response as requiring at least a one-minute
   fallback, with exponential escalation for repeated failures.

ACMM may add configured grace or choose a longer learned/admission delay, but it must not
shorten an authoritative provider wait.
