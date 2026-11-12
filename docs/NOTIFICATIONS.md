# Notifications – e-mail and a Teams channel

Reviews and approvals stall when nobody knows that something is waiting. The tool therefore tells people.
This needs the live tool running permanently (a server, or a PC that stays on); it is switched on in the server's start settings.

## What is sent
| Message | To | When |
|---|---|---|
| Review requested | Reviewers of the department (not the author) | A revision is submitted |
| Approval requested | Approvers | The review is passed |
| Ready to publish | Document controllers | The revision is approved |
| Changes requested | The author | A reviewer or approver returns the revision |
| Published | The author | The revision becomes the valid version |
| Review due soon / Review overdue | The process owner (if the owner's name matches a user), administrators and document controllers | 30 days before and after the review date |
| Summary of all open tasks | Each person who has open tasks | Weekly on Monday (or daily), at 08:00 server time |

* One message per person and check lists everything new. A task is announced **once**.
* The tasks are exactly those under **Dashboard ▸ My tasks**, so a message never asks for something the person cannot do.
* Each person can switch the messages off on the Dashboard.
* The optional Teams post goes to **one channel** and lists what is newly waiting (process ID, name, type of task). It contains no personal task lists.

## Switch on e-mail
1. Ask IT for the internal mail relay (host name and port) and a sender address the relay accepts, e.g. `processhub@example.com`.
2. In `deploy\windows\start_server.bat`:
   ```
   set "MEA_HUB_SMTP_HOST=smtp.example.com"
   set "MEA_HUB_SMTP_PORT=25"
   set "MEA_HUB_MAIL_FROM=processhub@example.com"
   set "MEA_HUB_PUBLIC_URL=https://processhub.example.com"
   ```
   With sign-in at the relay (port 587): additionally `MEA_HUB_SMTP_STARTTLS=1`, `MEA_HUB_SMTP_USER=…` and
   `MEA_HUB_SMTP_PASSWORD_FILE=<file only the service account can read>`.
   `MEA_HUB_PUBLIC_URL` puts a link to the process into each message.
3. Restart. **Administration ▸ Notifications ▸ Send me a test message.**
4. Addresses: people who sign in with Microsoft have theirs automatically. For local accounts enter the address under
   **Administration ▸ Users & roles**. The Notifications page lists who has none.

## Switch on the Teams channel post
1. In Teams open the channel ▸ **… ▸ Workflows ▸ "Post to a channel when a webhook request is received"** ▸ choose team and channel ▸
   copy the address that Teams shows.
2. Save the address in a text file that only the service account can read, e.g. `D:\MEAProcessHubData\teams_webhook.txt`.
   Anyone who knows this address can post to the channel, so treat it like a password.
3. `set "MEA_HUB_TEAMS_WEBHOOK_FILE=D:\MEAProcessHubData\teams_webhook.txt"` and restart.
4. **Administration ▸ Notifications ▸ Check now** posts as soon as something new is waiting.

## Options
| Setting | Default | Meaning |
|---|---|---|
| `MEA_HUB_NOTIFY_MINUTES` | 5 | How often the tool checks |
| `MEA_HUB_NOTIFY_DIGEST` | weekly | `weekly` (Monday), `daily` or `off` |
| `MEA_HUB_NOTIFY_DIGEST_HOUR` | 8 | Hour of the summary, server time |

## Good to know
* The first check after switching on announces what is already waiting – once.
* If the mail server is unreachable, the attempt is recorded as *failed* on the Notifications page and repeated at the next check.
* Messages contain process IDs, names and the type of task – no process content.
* The EXE on a personal PC only sends while it is running.

## What was tested
| Check | Result |
|---|---|
| New task → one message to the right person with a link, never twice; author is not asked to review own work; person can switch it off; mail server down → retried; weekly summary once; Teams card posted once | Automated test against a stand-in mail server and webhook, passes |
| Your mail relay, your Teams channel (the Workflows webhook), spam filtering of the sender address | **Not tested** – needs your environment |
