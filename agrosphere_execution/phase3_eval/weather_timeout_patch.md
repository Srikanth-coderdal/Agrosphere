# Patch: `main.py` — `httpx.AsyncClient` Timeout on `/api/weather` (~L166)

## Current (no timeout — indefinite hang risk)
```python
async with httpx.AsyncClient() as client:
    response = await client.get(weather_url, params=params)
```

## Fixed
```python
async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
    response = await client.get(weather_url, params=params)
```
`10.0` total, `5.0` connect is a reasonable default for a weather API call
— tune down further if your endpoint SLA is tighter. Consider also
catching `httpx.TimeoutException` around this call so a slow weather
provider degrades gracefully (e.g. weather data omitted from the scan
response) instead of the whole `/api/scan` request failing.

## Acceptance criteria
- [ ] `AsyncClient()` for the weather call has an explicit `timeout=`.
- [ ] A simulated slow/unreachable weather endpoint fails fast rather than hanging the request.

---

## Antigravity prompt

```
In main.py, find the httpx.AsyncClient() used in /api/weather (around
line 166) and add an explicit timeout:
httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)). Also wrap the
weather API call in a try/except for httpx.TimeoutException so a slow
weather provider doesn't fail the whole /api/scan request — just omit
weather data from the response and log a warning instead. Show me the diff.
```
