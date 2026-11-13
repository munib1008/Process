# Load test – how many people can work at the same time?

Status: measured 2026-11-13 with version 1.5.0 on a 4-core Linux machine, library of 183 processes (the delivered documents plus test
processes). Server and simulated users ran on the same machine, so read the figures as an estimate, not as a guarantee.

## Result
| Simultaneous users | Before (1.4.0): 95 % of actions within | After (1.5.0): 95 % of actions within | After: actions per second | Errors |
|---|---|---|---|---|
| 50 | 0.02 s | 0.02 s | 15 | 0 |
| 100 | **11.6 s** | 0.02 s | 29 | 0 |
| 200 | **20.5 s** | 0.03 s | 56 | 0 |
| 400 | not usable | 0.09 s | 113 | 0 |

"Simultaneous users" are people clicking every 3 seconds on average: 58 % open a process, 30 % open list pages (library, dashboard,
search, process tree), 12 % write (save a draft, post a comment). Real readers pause far longer between clicks, so 400 simulated users
stand for a clearly larger number of signed-in people.

## What was wrong and what was changed
1. **Cause.** In one Python process, several threads that fetch database rows at the same time take turns on the interpreter lock for every
   single row. Measured on the dashboard query: 95 per second one after the other, 65 per second with two at once, 12 per second with 48 at
   once. Up to about 50 users requests rarely overlapped; above that every list page stalled for seconds.
2. **Fix 1 – one at a time.** Short requests pass a gate one by one (each takes a few milliseconds). Long jobs – exports, imports, backup,
   restore, sign-in (password hashing), administration – stay outside the gate so that they hold nobody up.
3. **Fix 2 – fewer queries.** List pages asked the database three times per process; they now use four queries in total.
4. **Fix 3 – details.** One consistent read per page, a longer queue for waiting connections (the default of 5 made browsers retry for
   seconds), `synchronous = NORMAL` for the write-ahead log.

## What this means for PostgreSQL and a second server
*Recommendation: do not build it now.* The roadmap made the database change conditional on more than about 50 simultaneous editors. The
measured limit was not the database engine but the way requests overlapped, and it is removed. Reasons that would still justify the change:
- **Availability**, not capacity: a second node that takes over when the first fails. Today the answer is backup, restore drill and a restart.
- A library an order of magnitude larger (several thousand processes) **and** hundreds of simultaneous editors – measure first with
  `--from-data` on a copy of the real library.
- A group IT rule that only managed database servers may hold business data.

## Limits of the test (stated plainly)
- One machine for server and load; no real network, no HTTPS proxy, no browser rendering.
- 183 processes. List pages grow with the number of processes; repeat the test on a copy of your own library.
- The simulated users are threads of one Python process; above a few hundred the load generator itself becomes the limit.
- Exports and imports were not part of the mix. They run outside the gate; several large exports at once will slow other users noticeably.
- Not tested: Windows Server, IIS in front, anti-virus scanning of the data folder (it can slow SQLite considerably).

## Run it yourself
```
python tools/load_test.py                                   # 10, 25, 50, 100 users on the delivered documents
python tools/load_test.py --levels 50,100,200,400 --seconds 60 --report load.md
python tools/load_test.py --from-data D:\MEAProcessHub\data   # with a COPY of your own library; the original is not touched
```
The build runs a short version (20 and 60 users) and fails when 95 % of the actions take longer than 2 seconds or more than 1 % fail.
