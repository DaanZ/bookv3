# Roads: homework for growing yourself

Working name. A separate project that grows out of bookv3's quests. It turns a personal goal into
a road of short summaries (books, YouTube videos, blog articles), each followed by a small real-world
quest and a short reflection, and shows progress the way a role-playing game does: XP, levels,
skills and the things you are about to unlock.

bookv3 stays what it is, the place content is summarised and read. Roads is built on top of it and
reaches it only through its API.

Design reference: the "Snippers design" canvas, page "Ideas · Roads and the roadmap" (roadmap,
reflection, next book, character sheet, quest map, video and article readers).
https://claude.ai/artifact/CvG6T9GPCVny3YnfwWrqYQ

## Why

Therapy helps. But a session without homework mostly leaves you feeling heard: the insight fades by
Thursday. Growth needs something in between sessions that is small, concrete and repeated. Self-help
content could be that, but people consume it the way they consume everything else: one more video,
one more book, no change in behaviour.

Roads closes that gap with three rules:

1. **Every piece of content ends in something to do.** A quest with an observable done-when, never
   "reflect on your fears".
2. **Every step ends in a reflection, and the reflection picks the next step.** The road bends
   toward whatever is still in the way, instead of a fixed reading list.
3. **Progress is visible and ahead of you.** People love checking things off. What keeps them going
   is seeing what they are about to unlock, so the next unlock is always on screen.

## What it is not

- Not therapy, and it does not say it is. It is designed to sit next to therapy or coaching, and it
  can be used alone.
- Not a crisis tool. Any goal area that touches mental health links to real help in plain words and
  does not try to handle a crisis with a quest.
- Not a streak machine. Skipping is fine and is recorded, never punished. XP is never taken away.
  No loss framing ("you'll lose your streak!"), no countdowns, no pressure notifications.

## The loop

```
goal area ──▶ narrowed goal (≤2 sub-goals) ──▶ road (chapters of items)
                                                   │
      ┌────────────────────────────────────────────┘
      ▼
  item: book | video | article summary
      ▼
  3 quests (one per picked intelligence, each tied to a sub-goal)
      ▼
  reflection (3 questions, fixed answers + optional note)
      ▼
  next item chosen from the reflection ──▶ XP, skill progress, unlocks
```

1. **Onboarding.** Pick an area (communication, worrying less, focus and habits, confidence,
   relationships, leading people), then up to two sub-goals from a fixed list per area, plus an
   optional sentence in the person's own words.
2. **Road.** Chapters of 2–4 items each, a reflection after each item, and a *boss quest* that closes
   the chapter: a bigger real-world challenge ("a tiny morning habit on 10 of 14 days").
3. **Item.** Read or watch the summary in the reader (see Content).
4. **Quests.** Three per item. Pick one, or none.
5. **Reflection.** What did you try? Did it stick? What gets in the way now? The last answer picks
   the next item.
6. **Unlocks.** Finishing a chapter's boss opens the next chapter, a title and sometimes a new road.

## Content: three kinds, one reader

Everything is a summary in the same shape bookv3 already uses: `meta` plus `parts`, each part a
title and an HTML body whose `<b>` marks what matters. The reader treats all three the same:
paginated, highlighted, one unit of work per screen.

| Kind | Source | Parts are | Extra in `meta` | Link out |
|---|---|---|---|---|
| book | PDF (existing pipeline) | page ranges | author, publisher, pages | Hardcover |
| video | YouTube captions / transcript | time ranges | channel, duration, url, `start`/`end` per part | "Watch this part" opens at the timestamp |
| article | readable text of a blog post | sections | site, author, published, url | "Read the original" |

Video parts carry `start` and `end` in seconds so each summary page can jump into the video at the
right moment. A video is usually 3–5 parts, an article 1–3.

## The RPG layer

**XP** is earned for doing, not for time spent:

| Action | XP |
|---|---|
| Finish an article summary | 20 |
| Finish a video summary | 30 |
| Finish a book summary | 100 |
| Tiny / day / weekend quest done | 10 / 25 / 60 |
| Reflection written | 40 |
| Boss quest done | 150 |

A reflection earns more than any single summary on purpose: it is the homework.

**Levels** are overall: 100, 250, 450, 700, 1000 XP, then +350 each.

**Skills** are the goal's sub-goals (for focus and habits: starting routines, guarding attention,
deep focus, staying motivated), each with tiers I–III earned from the items and quests that feed
them. A second view shows which of the nine intelligences the person has actually practised
(from done quests), next to what they have read. The gap between the two is useful.

**Unlocks**, always previewed with what earns them:

- the next chapter of the road (after its boss)
- titles per skill tier ("Routine builder I")
- a new road branching off (habits → deep focus)
- a printable workbook of your own road, with your reflections (at a level)
- capstone quests that combine a whole chapter

Visual rules carried over from the Snippers design system: XP is the accent orange, never gold (gold
means a join and nothing else); locked things are dashed, never greyed-out text that fails contrast;
nothing celebrates with confetti.

## What bookv3 provides today

bookv3 is FastAPI over `books/*.json`, with profiles, PIN-minted device tokens and an ingest
pipeline (`api/routes/`):

- `GET /api/shelf`: every summary with state per reader
- `GET /api/books/{key}`: meta, parts (HTML), coals, position
- `PUT /api/books/{key}/position`, `POST /api/books/{key}/finish`: reading progress
- `POST /api/ingest/estimate`, `POST /api/ingest/upload`, `GET /api/ingest/jobs`: summarise a PDF
- `GET /api/profiles`, `POST /api/profiles/{id}/unlock`: who is reading, and the device token

Every reading endpoint needs `X-Profile` and, for a profile with a PIN, `X-Device`.

## What bookv3 must add for Roads

1. **A `kind` on every summary** (`book` default, `video`, `article`) and a `source` block (url,
   channel/site, duration, published). Existing books need no migration beyond the default.
2. **Video and article ingest** next to PDF ingest: fetch transcript or readable text, split into
   parts (by time for video), then the same `highlight_chunk` step. The same model rules apply: a
   model that returns summaries without `**` marks cannot run this pipeline.
3. **Tags per summary, generated once and cached in a sidecar**, the way quests are planned:
   - `intelligences`: fit 0–3 for each of the nine, with a reason
   - `gaps`: which reflection answers it answers ("I drift to my phone" → Indistractable)
   - `subgoals`: which fixed sub-goals it serves
   - `quests`: per part lesson, one quest per picked intelligence × sub-goal
4. **Access for another app.** Today a token belongs to one profile on one device. Roads needs an
   app-level credential (a service key the owner issues, scoped read-only to summaries and tags) and
   keeps its own users. Reading positions for Roads items live in Roads, not in bookv3.
5. **Search by tag**: `GET /api/items?subgoal=…&gap=…&kind=…`, so Roads can ask for "a video under
   15 minutes that answers 'I lose interest after a week'".

## What Roads owns

```json
// road: a person's path toward one goal
{"id": "r1", "profile": "p1", "area": "focus-and-habits",
 "subgoals": ["start-routines", "guard-attention"], "ownWords": "…",
 "chapters": [{"id": "c1", "title": "Understand the loop",
   "items": [{"kind": "book", "key": "The_Power_of_Habit", "state": "done"}],
   "boss": {"action": "…", "doneWhen": "…", "state": "done"},
   "unlocks": ["c2", "title:routine-builder-1"]}]}

// reflection: one per finished item
{"road": "r1", "item": "Make_Your_Bed", "tried": "Made my bed first thing, 12 of 14 mornings.",
 "stuck": "most-days", "gap": "drift-to-phone", "note": "Mostly after lunch.",
 "writtenAt": "2026-09-22T20:10:00Z"}

// xp ledger: append-only, never reduced
{"profile": "p1", "at": "2026-09-22T20:10:00Z", "xp": 40, "for": "reflection", "ref": "Make_Your_Bed"}
```

## Decisions already made in bookv3's quest work

- A quest must have an observable done-when.
- Three quests per item, one per intelligence picked for that item; each quest names the sub-goal it
  serves.
- Nine intelligences: Gardner's eight plus existential. Ties in an item's fit are broken toward the
  intelligences of the person's goal area.
- Sub-goals are a fixed list per area, so quests can be generated per item × sub-goal and cached.
  The person's own words rank and phrase, they never generate.
- The next item is chosen from the fixed "what gets in the way now?" answer, so no model call is
  needed at that moment. The optional note only breaks ties.
- Quests come back as revisits after about 3, 10 and 30 days.

## First tester: Daan's road

From a questionnaire on 30 September 2026. The first road Roads should run end to end.

- **Area:** focus and habits.
- **Wants:** finish what I start, ship regularly, a daily build routine, and good routines during
  the day: workout, meditation, writing down ideas.
- **In the way:** interest fades after about a week, because the fun part (the design) is done and
  what is left is grind.
- **Time:** varies a lot, so every quest needs tiny, day and weekend sizes.
- **Format:** book summaries.
- **Tested on:** Roads itself, so the boss quests are Roads' own first steps.

Most of the relevant books are already read (The Power of Habit, Make Your Bed, Deep Work, Grit, Big
Magic, The Miracle of Mindfulness), which is the whole case for Roads: the knowing is done, the doing
is not. The road therefore mixes *revisits* (a quest on a book already read, no re-read) with three
new books.

| Chapter | Finish and ship | Daily rhythm | Boss |
|---|---|---|---|
| 1 Start the rhythm | Make Your Bed (revisit): fixed 25-minute Roads slot each morning | How to Take Smart Notes (new): one idea note at the end of every slot | slot plus note on 10 of 14 days |
| 2 Past the fun part | Grit (revisit): the dull rest of step 1 as 30-minute tasks | The Miracle of Mindfulness (revisit): 5 minutes sitting before the slot | ship Roads step 1 before any new idea gets a repo |
| 3 Done beats good | Big Magic (revisit): put out something unfinished-looking | Upgrade Yourself (new): 20 minutes of movement stacked on the slot | ship step 2, video ingest on five videos, rough is fine |
| 4 Ship to someone | Bootstrapper's Handbook (new): show Roads to one real person | Deep Work (revisit): two fixed deep blocks a week | one road running end to end for one tester |

Two rules this road adds to the design: a *revisit* is a first-class item (quests without a re-read),
and new routines arrive one per chapter, stacked on an existing one, never all at once.

## Open questions

- Is a road one goal forever, or can a person run two roads side by side?
- Does a therapist or coach get a view of the road (with the person's consent), and what may they
  add to it: their own homework items?
- Which YouTube and blog sources are allowed in? A curated list per area keeps quality and avoids
  summarising content whose licence forbids it.
- How are summaries of other people's videos and articles credited and linked, so the original
  creator gains a viewer rather than losing one?
- Does XP cross roads (one character), or is each road its own character?

## First steps

1. In bookv3: add `kind` and `source` to the summary format, with `book` as the default.
2. In bookv3: one video ingest path (captions → parts with `start`/`end` → highlight) and try it on
   five habit videos.
3. In bookv3: the tags sidecar for the ten self-help books already used in the quest designs.
4. New repo: Roads with its own users, calling bookv3 with a service key, starting with one road
   (focus and habits) end to end: onboarding, one chapter, reflection, XP ledger.
