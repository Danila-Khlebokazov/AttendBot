# Auto-Attend for WSP

Automatically attend for a subject and send a message via Telegram bot. Supports **one or many users** at once: each person gets their own WSP account and Telegram notifications.

## Quick Start

1. **Install Docker** for your OS
   [https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)

2. **Create and fill environment**

   ```bash
   cp .env.example .env
   ```

   * Get **bot token** from **@BotFather** (one bot is used for all users).
   * Put the token into `.env`:

     ```
     TG_BOT_TOKEN=...
     ```

3. **Configure users** (choose one)

   * **Single user** — put in `.env`:

     ```
     WSP_LOGIN=...
     WSP_PASSWORD=...
     TG_CHAT_ID=...   # from @userinfobot or @chatid_echo_bot
     ```

   * **Multiple users** — create `users.toml` from the example:

     ```bash
     cp users.toml.example users.toml
     ```

     Edit `users.toml` and add one `[[user]]` block per person:

     ```toml
     [[user]]
     wsp_login = "student_one"
     wsp_password = "password1"
     tg_chat_id = "123456789"

     [[user]]
     wsp_login = "student_two"
     wsp_password = "password2"
     tg_chat_id = "987654321"
     ```

     Each user runs in a separate thread with their own browser session; all share the same schedule.

4. **Edit schedule**
   Update time windows and timezone in `schedule.toml` (defaults are included). Example:

   ```toml
   timezone = "Asia/Almaty"

   [defaults]
   windows = ["07:00-19:00"]

   [weekdays.monday]
   enabled = true
   windows = ["07:00-12:00", "13:00-15:00"]

   [weekdays.saturday]
   enabled = false

   [weekdays.sunday]
   enabled = false
   ```

5. **Build & run with Docker Compose (choose your profile)**

   * **Apple Silicon / ARM64**:

     ```bash
     docker compose --profile arm64 up --build -d
     ```
   * **Intel/AMD (x86_64)**:

     ```bash
     docker compose --profile amd64 up --build -d
     ```

6. **Watch logs**

   ```bash
   docker compose logs -f bot
   ```

   You should see startup logs and a Telegram “Bot starting” message.

---

## Configuration

### `.env` keys

| Key             | Required      | Example                                  | Notes                                                                 |
| --------------- | ------------- | ---------------------------------------- | --------------------------------------------------------------------- |
| `TG_BOT_TOKEN`  | ✅             | `123456:ABC...`                          | From @BotFather (used for all users)                                  |
| `WSP_LOGIN`     | ⚠️ single-user | `a_student`                              | WSP username (required only if not using `users.toml`)                |
| `WSP_PASSWORD`  | ⚠️ single-user | `********`                               | WSP password (required only if not using `users.toml`)                |
| `TG_CHAT_ID`    | ⚠️ single-user | `123456789`                              | Telegram chat ID (required only if not using `users.toml`)            |
| `USERS_PATH`    | ⛔️            | `users.toml`                             | Path to multi-user config; if present and non-empty, overrides .env   |
| `REMOTE_URL`    | ⛔️ (defaults) | `http://selenium:4444/wd/hub`            | Selenium WebDriver URL                                                  |
| `BASE_URL`      | ⛔️            | `https://wsp.kbtu.kz/RegistrationOnline` | WSP page                                                               |
| `SCHEDULE_PATH` | ⛔️            | `schedule.toml`                          | Path to schedule file (shared by all users)                           |
| `LOG_LEVEL`     | ⛔️            | `INFO` or `DEBUG`                        | Logging level                                                          |

For **multi-user**, create `users.toml` (see `users.toml.example`). The bot runs one worker thread per user; ensure Selenium has enough capacity (e.g. `SE_NODE_MAX_SESSIONS` in docker-compose).


### `schedule.toml`

* `timezone` must be a valid IANA zone (e.g. `Asia/Almaty`).
* Each weekday can be `enabled=true/false`.
* Time windows `"HH:MM-HH:MM"`. Multiple windows per day are supported.
* Overnight windows are supported (e.g. `"22:00-02:00"`).

---

## Common Commands

* **Start (ARM64)**
  `docker compose --profile arm64 up --build -d`
* **Start (AMD64)**
  `docker compose --profile amd64 up --build -d`
* **Stop**
  `docker compose down`
* **Logs**
  `docker compose logs -f bot`
* **Restart only the bot**
  `docker compose restart bot`
