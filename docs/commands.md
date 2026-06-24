# Cadence — Command reference

This document is the in-depth guide to every Cadence slash command: what each one
does, when to use it, how it interacts with queue state, loop modes, and idle
timeouts, and what replies or errors you should expect.

For a short summary inside Discord, use `/help`.

**Requirements common to most commands**

- Cadence must be online in your server (only one bot process should run at a time).
- Most playback commands require **you** to be in a voice channel when you invoke
  them; the bot joins or moves to **your** channel.
- State is **per guild** (per Discord server): each server has its own queue,
  volume, loop mode, and idle timer. Nothing persists across a bot restart.
- The queue holds at most **30** upcoming tracks in addition to whatever is
  currently playing.

---

## Queue numbering

Cadence uses **1-based** positions everywhere (`/queue`, `/remove`):

| Position | Meaning |
|----------|---------|
| **1** | The track playing right now (or the only track if nothing is actively playing but a current track is set) |
| **2** | Next up |
| **3+** | Further upcoming tracks |

`/queue` always lists position **1** as “now playing” when a current track exists,
then numbers upcoming items starting at **2**.

---

## Playback commands

### `/play`

**Purpose:** Search YouTube or play from a direct URL.

**Parameters**

- `query` — Free text (e.g. `lofi hip hop`) or a full YouTube URL (`https://…`).

**Behavior**

1. You must be in a voice channel; otherwise Cadence replies ephemerally:
   *“You need to be in a voice channel first.”*
2. Cadence defers the reply (lookup can take a few seconds).
3. The bot connects to your voice channel (or moves if already connected elsewhere
   in the guild).
4. Cadence resolves the query via yt-dlp:
   - URLs are fetched directly.
   - Plain text is treated as a YouTube search; the **first** result is used.
5. **If nothing is playing:** the track starts immediately. You get
   `▶️ Now playing: **Title**`.
6. **If something is already playing or queued as current:** the track is
   **enqueued**. You get `➕ Added to queue: **Title**`. Playback order is
   unchanged until the current song finishes or is skipped.
7. If the upcoming queue already has **30** tracks, Cadence refuses:
   *“Queue is full — remove something first.”* (ephemeral before defer, or as a
   follow-up if the queue filled during the request.)
8. If lookup fails: *“Couldn't find anything for that.”*

**Notes**

- Cadence does **not** expand playlists from a watch URL; `&list=…` is ignored and
  only that single video plays.
- “Now playing” announcements for queued adds go to the text channel where
  `/play` was last used successfully in that guild.
- Using `/play` records guild activity for the idle timer (see `/idle`).

---

### `/forceplay`

**Purpose:** Drop everything and play a new track **now**.

**Parameters**

- `query` — Same as `/play` (search or URL).

**Behavior**

1. Same voice-channel and fetch requirements as `/play`.
2. **Clears the entire queue**, disables loop mode, and clears the “current track”
   slot via `reset_lineup`.
3. Enqueues only the new track and starts it immediately.
4. If audio was already playing or paused, the voice client is stopped first so
   the new song begins cleanly.
5. Reply: `▶️ Now playing: **Title**`.

**When to use it**

- A DJ wants to override the queue without manually `/clear` + `/play` + `/skip`.
- You need a hard reset of what’s lined up without calling `/stop` (which also
  disconnects).

**Caution**

- Loop mode is reset to **Off**. Set `/loop` again if you still want looping.

---

### `/move`

**Purpose:** Move the bot to your voice channel without starting playback.

**Parameters**

- None.

**Behavior**

1. You must be in a voice channel.
2. Cadence joins your channel, moves from another channel in the same guild, or
   reports it is already there:
   - `Joined **channel-name**.`
   - `Moved **channel-name**.`
   - `Already in **channel-name**.`

**When to use it**

- The bot is in the wrong voice channel but you want to reposition it before
  `/play`.
- You moved to another channel and want the bot to follow without queuing music.

**Notes**

- Does not stop or start playback by itself.
- Does not clear the queue.

---

### `/skip`

**Purpose:** End the current song early and advance as if it had finished naturally.

**Parameters**

- None.

**Behavior**

1. If nothing is actively playing: ephemeral *“Nothing is playing.”*
2. Otherwise Cadence stops the voice stream. The current track is **not** cleared
   first—`play_next` runs with the finished track still set, same as a natural
   end-of-song transition.
3. Reply: `⏭️ Skipped.`
4. The next track starts automatically via the internal `play_next` chain (with a
   “now playing” post if configured).

**Interaction with loop**

- **Off:** plays the next queued track; the skipped song is not reinserted (same
  as letting it finish).
- **Queue / queue-shuffle:** the skipped song is reinserted into the queue (end
  or random slot) before the next track plays—it is **not** removed from rotation.
- **Current song (track loop):** skip turns loop **Off**, then advances to the
  next queued item (or goes idle if the queue is empty). The looped song does not
  replay again on this skip.

---

### `/pause`

**Purpose:** Pause audio at the current position.

**Parameters**

- None.

**Behavior**

1. If not playing: ephemeral *“Nothing is playing.”*
2. Pauses the voice client. Reply: `⏸️ Paused.`

**Notes**

- Idle timers **keep running** while paused; pausing does not reset activity
  clocks.
- `/resume` continues from the same stream position (Discord/FFmpeg permitting).

---

### `/resume`

**Purpose:** Resume after `/pause`.

**Parameters**

- None.

**Behavior**

1. If not paused: ephemeral *“Nothing is paused.”*
2. Resumes playback. Reply: `▶️ Resumed.`

---

### `/stop`

**Purpose:** Full shutdown of playback in the guild.

**Parameters**

- None.

**Behavior**

1. Clears the queue and current track.
2. Sets loop mode to **Off**.
3. Resets idle settings to defaults (10 minutes) and clears activity timestamps.
4. Stops audio and **disconnects** from voice.
5. Reply: `⏹️ Stopped and left the channel.`

**When to use it**

- End the session entirely.
- Unlike idle disconnect, `/stop` is immediate and user-initiated.

**Contrast with idle auto-disconnect**

- Idle timeout also calls the same `stop()` path, so cleanup is identical.

---

## Queue commands

### `/queue`

**Purpose:** Show what is playing and what is lined up.

**Parameters**

- None.

**Behavior**

- If empty: *“The queue is empty.”*
- Otherwise a numbered list:
  - Line 1: `1. ▶️ Now playing: **Title**` (when something is current)
  - Following lines: upcoming tracks, up to the queue cap display.

**Notes**

- Read-only; does not mutate state.
- Position numbers match `/remove` (see Queue numbering above).

---

### `/nowplaying`

**Purpose:** Show only the active track, with who requested it.

**Parameters**

- None.

**Behavior**

- If nothing current: *“Nothing is playing.”*
- Otherwise: `▶️ **Title** (@user)` — mentions the requester’s Discord user.

**Contrast with `/queue`**

- `/nowplaying` is a single-line status; `/queue` is the full ordered list.

---

### `/remove`

**Purpose:** Remove a track by its display position.

**Parameters**

- `position` — Integer **1** to **31** (1 = now playing; 2–31 = upcoming slots
  when something is playing).

**Behavior**

- **Position 1 while something is playing:** removes/skips the current track
  (stops playback and advances similarly to `/skip` for that item). Reply:
  `Skipped **Title**.`
- **Position 2+:** removes that upcoming entry without stopping the current song.
  Reply: `Removed **Title** from the queue.`
- Invalid position: ephemeral *“No track at position **N**.”*
- Nothing to remove: ephemeral *“Nothing is playing.”*

**Tips**

- Run `/queue` first to see exact positions.
- Removing the last upcoming track while something plays leaves only the current
  song; when it ends, behavior depends on `/loop` mode.

---

### `/clear`

**Purpose:** Wipe upcoming tracks but keep the current song.

**Parameters**

- None.

**Behavior**

- Removes all **queued** (not currently playing) tracks.
- If already empty: *“Queue is already empty.”*
- Otherwise: `Cleared **N** track(s).`

**Notes**

- Does **not** change loop mode.
- Does **not** stop playback.
- Useful when you want to let the current song finish but discard the rest.

---

## Settings commands

### `/loop`

**Purpose:** Control what happens when a track finishes naturally or is skipped
via `/skip` (same advance logic). `/remove 1` still clears the current track
before advancing.

**Parameters**

- `mode` — One of four choices:

| Mode | Label in Discord | Behavior when a song ends |
|------|------------------|---------------------------|
| `off` | Off | Play next queued track; if queue empty, stay in channel idle (no song). |
| `track` | Current song | Replay the same track again. |
| `queue` | Queue | Move finished track to **end** of queue, play next; if queue was empty, replay same track back-to-back. |
| `queue_shuffle` | Queue shuffle | Reinsert finished track at a **random** position among upcoming slots (never position 0 / immediate replay slot when others exist); if queue empty, replay same track. |

**Reply**

- `Loop set to **Off**.` (or Current song / Queue / Queue shuffle).

**Details**

- **Track loop** does not dequeue; `/queue` still shows the same item at position 1.
- **Queue loop** cycles the whole set: over time every track returns to the tail
  and plays again in order.
- **Queue shuffle** randomizes where the finished song lands among upcoming items;
  when only one song exists in rotation, back-to-back replay is allowed.
- `/forceplay` and `/stop` reset loop to **Off**.
- `/clear` does not change loop mode.

---

### `/volume`

**Purpose:** Set playback loudness for the guild.

**Parameters**

- `level` — Integer **0** (silent) to **100** (full). Values above 100 are
  rejected ephemerally: *“Volume must be between 0 and 100.”*

**Behavior**

- Updates guild volume state.
- If audio is playing, the live stream volume changes immediately.
- Reply: `🔊 Volume set to **N**.`

**Notes**

- Default volume for new guilds comes from the `CADENCE_DEFAULT_VOLUME` environment
  variable (often 50).
- Volume persists for the guild until changed or the bot restarts.

---

### `/idle`

**Purpose:** Configure automatic disconnect after inactivity.

**Parameters**

- `minutes` — **1** to **1500**. Default behavior uses **10** minutes when unset
  or after `/stop`.

**Behavior**

- Sets `idle_minutes` for the guild.
- Reply: `Auto-disconnect idle time set to **N** minutes.`

**When auto-disconnect runs**

Cadence checks roughly every 30 seconds while connected to voice. Disconnect
(equivalent to `/stop`) happens if **either**:

1. **Activity timeout** — Both conditions are true:
   - No new song has **started** for longer than `idle_minutes`, **and**
   - No Cadence slash command has been used in the guild for longer than
     `idle_minutes`.
2. **Alone timeout** — The bot is the only non-bot member in its voice channel
   for longer than `idle_minutes`.

**What resets activity**

- Any slash command in the guild (including `/help`, `/queue`, etc.) updates
  “last command” time.
- Starting playback updates “last song started” time.
- Someone joining the voice channel clears the “alone” timer.

**What full disconnect clears**

- Queue, current track, loop mode, voice connection, and idle timer (back to 10
  minutes with fresh activity clocks).

**Edge cases**

- Paused playback still counts as “last song started” until skip/stop.
- Bot not in voice: idle checks do not apply.
- Only one bot process should run; idle state is in-memory per process.

---

## Help

### `/help`

**Purpose:** Post a concise categorized list of all commands in the channel.

**Parameters**

- None.

**Behavior**

- Public reply with short descriptions grouped as Playback, Queue, and Settings.
- For full detail, see this document (`docs/commands.md`).

---

## Common workflows

### Start a listening session

1. Join a voice channel.
2. `/play` your first song.
3. `/play` more songs to build a queue.
4. `/queue` to inspect order; `/volume` as needed.

### Take over as DJ

1. `/forceplay` to immediately switch to your pick (clears queue).
2. Or `/remove` / `/clear` to edit the existing line-up without disconnecting.

### Loop a single song

1. `/play` the track.
2. `/loop` → **Current song**.

### Loop a whole set

1. Queue multiple tracks with `/play`.
2. `/loop` → **Queue** (ordered cycle) or **Queue shuffle** (random reinsert).

### End or walk away

- `/stop` — immediate leave and reset.
- `/idle 5` — leave after 5 minutes of no commands **and** no new playback, or if
  alone in channel for 5 minutes.

---

## Error messages quick reference

| Message | Typical cause |
|---------|----------------|
| You need to be in a voice channel first. | `/play`, `/forceplay`, or `/move` without joining voice |
| Nothing is playing. | `/skip`, `/pause`, `/nowplaying`, or `/remove` with no active track |
| Nothing is paused. | `/resume` when not paused |
| Queue is full — remove something first. | 30 upcoming tracks already |
| Couldn't find anything for that. | yt-dlp failed or no results |
| No track at position **N**. | `/remove` with invalid index |
| Volume must be between 0 and 100. | `/volume` out of range |
| Something went wrong. | Unexpected server error (check bot logs) |

---

## Operator notes

- **FFmpeg** must be installed and on `PATH`.
- **Voice States** intent should be enabled in the Discord Developer Portal for
  idle alone-detection.
- Run a single instance: `python -m cadence` (instance lock prevents duplicates).
- Slash commands sync on bot ready; guild-specific sync is faster during development
  when `DISCORD_GUILD_ID` is set.
