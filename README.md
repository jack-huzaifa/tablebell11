# TableBell — QR Ordering + Kitchen Bell System

A working web application that lets restaurants replace order-taking waiters with:
1. QR code ordering (customers scan, browse menu, order from their phone)
2. A real-time kitchen dashboard that "rings" (plays a sound) when a new order arrives
3. A live wait-time countdown shown to the customer, set manually by the cook
4. A runner/waiter screen showing only orders ready for delivery

This has been fully built and tested end-to-end. Every core workflow described in your
plan works: signup → menu setup → QR code generation → customer ordering → kitchen alert →
wait time → ready → runner delivery → status tracking.

---

## How to Run This Locally (on your own computer)

### 1. Requirements
- Python 3.9 or newer installed on your computer

### 2. Setup (one-time)
Open a terminal/command prompt in this folder and run:

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

You'll see output ending in something like:
```
* Running on http://127.0.0.1:5050
```

### 4. Open it in your browser
Go to: **http://localhost:5050**

---

## How to Use It (Walkthrough)

### As the restaurant owner:
1. Go to `http://localhost:5050` and click **"Get Started Free"**
2. Sign up with your restaurant name, email, and password (a demo menu and 3 tables are
   created automatically so you have something to test with)
3. You'll land on the **Admin Dashboard** where you can:
   - Add/edit/remove menu items (name, category, price, description)
   - Add tables and instantly get a QR code for each one
   - Click "Open / Test" under any table's QR code to see exactly what a customer sees
   - Change your subscription plan (Starter/Growth/Pro)

### As the kitchen:
1. From the Admin Dashboard, click **"🔔 Kitchen"** in the top navigation
2. Keep this page open on a tablet or laptop near the cook, with the volume up
3. When a new order comes in, you'll hear a bell sound and see the order appear automatically
4. Tap a wait-time button (5/10/15/20 min or Custom) — this starts the customer's countdown
5. When food is ready, tap **"Mark Ready for Pickup"**

### As the runner/waiter:
1. Click **"🏃 Runner"** in the top navigation
2. **The first time you open this on any device/phone, it will ask "Who's working this
   device?"** — type a name (e.g. "Priya"). This is saved on that phone only, no login or
   password needed, and lets your teammates see who's handling what.
3. This screen has TWO sections:
   - **🙋 Table Requests** — refills, napkins, assistance, or the check, sent directly by
     customers.
   - **✅ Food Ready for Delivery** — orders marked ready by the kitchen.
4. **If your restaurant has multiple waiters/runners, here's how duplicate notifications
   are handled** (see full explanation below): every request/order shows a **"🙋 Claim
   This"** button. The first person to tap it locks it to their name, and everyone else's
   screen instantly shows "🔒 Claimed by [name]" instead of a claim button — so nobody
   else wastes a trip going to the same table.
5. Once you've claimed something and handled it, tap **"Mark Delivered"** or **"Resolved"**.
6. Each section plays its own distinct sound so staff can tell by ear whether it's a food
   pickup or a table request, without needing to look at the screen constantly.

### How multiple waiters know WHO should go (Table Sections) — AND why staff count still drops

Important: sections are NOT about matching the old 1-waiter-per-5-tables staffing ratio.
**One runner using TableBell can cover far more tables than a traditional waiter**, because
the traditional bottleneck — walking to the table, taking the order, remembering it,
walking it to the kitchen — is gone entirely. What's left per table is just "deliver food
when it's ready" and "handle the occasional refill/napkin request." That's a much lighter
job, which is *why* the labor cost actually drops.

Concretely: a 20-table full-service restaurant traditionally needs 4-6 waiters (1 per
4-5 tables). With TableBell, **2 runners covering 10 tables each** is a realistic, tested
setup — that's the actual headcount reduction that saves the owner money, not just a
reshuffling of the same number of people.

**The Sections page reflects this directly:**

1. **At the start of a shift**, go to the **"🗂️ Sections"** page (linked from Admin,
   Kitchen, and Runner navigation). Instead of assigning tables one at a time, you
   **select a whole group of tables** (e.g. tick tables 1 through 10) and assign them all
   to one runner in a single click — "Priya: tables 1-10." Do the same for your second
   runner with the remaining tables. A 20-table restaurant covered by 2 people takes about
   30 seconds to set up this way, not 20 separate clicks.
2. **The page shows a live stat strip** — total tables, how many runners are assigned,
   how many tables are still unassigned, and the average tables-per-runner — so an owner
   can see at a glance whether their staffing is realistic (e.g. "2 runners, 10 tables
   each" confirms they've actually reduced headcount, not just relabeled the same waiters).
3. **From that point on, routing is fully automatic**: when a customer at Table 7 requests
   a refill, or the kitchen marks Table 7's food ready, the system already knows it's
   Priya's table (since it's in her assigned range) and shows it on **her** runner screen
   as "✅ Your Table" — no claiming, no racing, no ambiguity. Other runners see it as
   "🔒 Priya's Table" instead.
4. **If a table has nobody assigned** (e.g., an extra table, or sections haven't been set
   up yet), it falls back to the **claiming system**: the first available runner to tap
   "🙋 I'll Take This" gets it.
5. **If Priya is busy, on break, or missed it**, any other runner can tap **"Cover For
   Them"** to step in without anything getting stuck waiting on one person.
6. **At the end of a shift**, click **"🔄 End of Shift — Clear All Assignments"** to reset
   everything for the next shift's staff.

This has been tested end-to-end at realistic scale: a 20-table restaurant with tables
bulk-assigned in two single actions — 10 tables to Priya, 10 tables to Raj — confirming
requests from tables in each range automatically routed to the correct runner, exactly
as they would with any table count.

### How multiple waiters/runners avoid duplicate trips (backup for unassigned tables)

For any table without a section assignment, or if you prefer a fully open "whoever's
free grabs it" model instead of sections, the original claiming system still works:

If a restaurant has 2-3 people using the Runner screen at once (e.g. on their own phones),
everyone sees every new request/ready order at the same time — this is intentional, since
you don't know in advance who's free. But without a way to signal "I've got this," you'd
risk two waiters walking to the same table while another table's request sits ignored.
**This is solved with a claiming system:**

- **Claim** — the first person to tap "🙋 Claim This" on a request or order locks it to
  their name. This uses an atomic database update, so even if two waiters tap at the
  exact same instant, only one of them will actually win the claim — tested and confirmed
  with 5 simultaneous simulated claim attempts on the same request, and exactly one
  succeeded every time.
- **Claimed by you** — shows in purple on your own screen with a "Mark Delivered/Resolved"
  button and a "Release" option (in case you realize you can't actually get to it).
- **Claimed by someone else** — shows on everyone else's screen as "🔒 Claimed by [name]"
  (dimmed out) with a **"Take Over"** button instead of a claim button — so if that person
  gets stuck, busy, or forgets, someone else can step in without anything getting
  permanently stuck.
- No accounts, passwords, or admin setup needed for waiters — each phone/device just
  remembers the name typed in once, stored locally on that device.

### How refills actually get fulfilled (the important part)

A "refill" is not one single thing — it splits into two very different operational paths,
and the system automatically figures out which path to use for each menu item:

| Type of refill | Example | How it's handled |
|---|---|---|
| **Instant item** (already available, no cooking needed) | Water, fountain soda/iced tea, bread basket | Skips the kitchen completely. Goes **straight to the runner** as an instant alert with the exact item name and quantity (e.g. "1x Iced Tea"), since it's just grabbing something already made. |
| **Kitchen-made item** (needs to be cooked/prepared) | Pizza, fries, pasta, a cooked entrée | Creates a **real order that goes through the normal kitchen pipeline** — bell rings on the kitchen dashboard, the cook sets a wait time, the customer sees a live countdown just like a fresh order, then it's marked ready and sent to the runner to deliver. |

**As the restaurant owner, you control this per menu item** in the Admin dashboard: each
item is tagged either "Kitchen-made" or "Instant refill" (you can flip this anytime with
one click). This matters because reordering fries genuinely takes cook time and should
show the customer an honest wait estimate, while asking for more water should never make
someone wait for the kitchen.

### Customer experience:
1. On the menu page or the live order-status/countdown screen, every customer sees a
   **"🙋 Need Something?"** button.
2. Tapping it shows **every item from the menu** with a one-tap **"+1 More"** button next
   to each — so the customer picks the *exact* item they want more of (not a vague generic
   "drink refill" button), and staff know precisely what to bring.
   - Tapping "+1 More" next to Iced Tea → instantly alerts the runner: "1x Iced Tea for
     Table 3"
   - Tapping "+1 More" next to Margherita Pizza → creates a real kitchen order; the
     customer sees the same "Preparing... ready in X min" countdown as a fresh order
3. Below that, there are also quick buttons for **Napkins/Utensils, Call for Assistance,
   Get the Check**, plus a free-text box for anything else (e.g. "can we get a
   highchair?") — these always go straight to the runner since they're not menu items.
4. The customer sees an on-screen confirmation so they know it went through — no need to
   keep flagging someone down.
5. If a customer taps the same non-item request type twice in a row before it's resolved,
   it won't create a duplicate entry (tested and confirmed) — it just tells staff it's
   still pending.

### As a customer (testing):
1. On the Admin Dashboard, click "Open / Test" under any table, OR scan the printed QR code
   with your phone camera
2. Browse the menu, add items with the +/− buttons, optionally add a note per item
3. Tap **"Place Order"** at the bottom
4. You'll see a live status screen: "Order Received" → "Preparing" (with a live countdown
   timer) → "Ready!" → "Delivered" — this updates automatically every 3 seconds, no refresh
   needed

---

### Menu Analytics — see which items get ordered, and how often

A new **"📊 Analytics"** page (linked from every screen's navigation) shows the owner
exactly which menu items are selling, automatically calculated from every order placed —
no manual counting needed.

1. **Ranked list of best-sellers**, showing for each item: total quantity ordered, how
   many separate orders it appeared in, and total revenue generated — sorted from most to
   least ordered, with a visual bar so the gap between top and bottom sellers is obvious
   at a glance.
2. **Refills are automatically merged with the original item.** If a customer ordered a
   Margherita Pizza and later tapped "+1 More" for another one, this shows as "Margherita
   Pizza: 2×" in the rankings (not two separate line items), with a small tag showing how
   many of those were refills specifically — useful for spotting items people love enough
   to ask for seconds.
3. **Three time filters**: Today, Last 7 Days, All Time — so an owner can check what's
   selling on a given night versus long-term trends.
4. **"Never Ordered" section** flags any menu item that had zero orders in the selected
   period — a direct signal for the owner to consider promoting, redesigning, or removing
   that item.
5. **A "Top Sellers Today" quick-view widget** also appears right on the main Admin
   dashboard (top 5 items) so the owner doesn't have to navigate away to see today's
   at-a-glance picture, with a link through to the full Analytics page.

This has been tested end-to-end: placed multiple orders including different items and
quantities, plus a "+1 More" refill of an already-ordered item, and confirmed the
analytics correctly merged the refill into the same item's total count, calculated
accurate revenue, correctly filtered by Today/Week/All Time, correctly flagged
never-ordered items, and correctly kept one restaurant's analytics fully isolated from
another's (tested and confirmed).

## Augmented Reality Menu Preview

Customers can see a life-size, rotatable 3D preview of a dish before ordering — directly
from their phone's camera, with **no app download required**. This uses **WebAR**: on
iPhone this is Apple's built-in "AR Quick Look," on Android it's Google's built-in
"Scene Viewer" — both triggered from a normal web page, consistent with this product's
core principle of zero-install customer experience.

### Business model: a loyalty perk, not a day-one feature

AR menu preview is **deliberately gated behind subscription tenure**, not offered to
every restaurant from signup. A restaurant unlocks it only after being an **active,
paying subscriber for 3 months or more** (configurable via `AR_UNLOCK_AFTER_MONTHS`) —
trial time does not count. This is a real product/business decision, not just a
marketing framing:

- **Cost alignment**: real 3D food models cost real money per dish (see cost breakdown
  below); gating the feature to proven, retained customers means that cost is only spent
  where a relationship has already shown it will last, not on every trial signup.
- **A natural upsell/re-engagement moment**: rather than a static subscription with no
  reason to check back in, this creates a genuine "you've unlocked something new" touch
  point a few months into the relationship — a good moment for you to reach out, offer
  to help set it up, and reinforce the relationship without a hard sales pitch.
- **Enforced server-side, not just hidden in the UI**: the eligibility check happens in
  the backend route that saves AR model URLs, not just by hiding the form — confirmed by
  testing that a direct POST request to the AR-update endpoint is silently rejected (and
  the item's existing data left untouched) if the restaurant hasn't unlocked the feature,
  even if someone bypasses the on-screen form entirely.
- **A manual override flag** (`ar_unlock_override`) exists for exceptions — e.g. a demo
  account, a goodwill gesture, or a specific negotiated deal — without changing the
  default tenure-based rule for everyone else.

### What this looks like in the app

- **Before unlocking**: the Admin dashboard shows a locked message ("AR menu preview
  unlocks as a loyalty perk after 3 months as an active subscriber, ~X months to go")
  instead of the AR input fields, and the customer-facing menu never shows an AR button
  for that restaurant, even if a model happens to be attached to an item behind the
  scenes (e.g. the demo data described below).
- **After unlocking**: the full AR controls appear in Admin, and eligible items show the
  "View in 3D / AR" button to customers.
- **Demo Mode testing tools**: since real tenure takes months to accrue, two buttons
  exist for testing only (never exposed outside Demo Mode): "🧪 Demo: Unlock Now"
  (instantly grants access, simulating 3+ months of subscription) and "🧪 Demo: Reset
  Lock" (reverts back to the normal tenure gate) — useful for showing the full
  locked-to-unlocked experience live in a demo without waiting months.

### How it works

1. The restaurant owner attaches a 3D model file to any menu item in the Admin dashboard
   — a `.glb` file (used by Android) and/or a `.usdz` file (used by iPhone). Both are
   optional and can be added, edited, or removed independently per item at any time.
2. On the customer's menu page, any item with a model attached shows a **"📱 View in 3D
   / AR"** button.
3. Tapping it opens a modal with an interactive, rotatable 3D model (powered by Google's
   open-source `model-viewer` web component — the same underlying technology used by
   commercial AR menu products).
4. A second button inside that modal — **"View on Your Table (AR)"** — launches the
   phone's native AR viewer, placing a life-size version of the dish on the real table
   using the camera, with no app install.

### What's included as a working demo

Every new signup's demo menu includes one item, **"Avocado Toast,"** with a real, live
3D model already attached (sourced from Khronos Group's public glTF sample model
library) — this lets anyone testing the app see the full AR flow working immediately,
with zero setup.

### The honest cost/scope reality (important for anyone evaluating this feature)

Building this technical capability into the app was straightforward and is fully
functional. **Populating it with real, professional 3D models for an entire restaurant
menu is a separate, real cost** that this project does not eliminate:

- Professional 3D food model creation (photogrammetry scanning of an actual dish)
  typically costs **$49-500+ per dish** from specialized vendors, or requires the
  restaurant/founder to learn a 3D scanning workflow using phone photos and free tools
  (e.g. Meshroom, an open-source photogrammetry tool) — a real time investment, not a
  quick task.
- A full menu (30-40 items) professionally scanned would cost roughly **$3,000-12,000**
  for a "hero dishes only" subset, or **$8,000-25,000** for full menu coverage, per
  industry vendor pricing researched for this feature.
- Industry-reported ROI for AR menus (20-26% average order value increase, per published
  vendor data from companies like Kabaq) is a real, plausible mechanism — customers
  ordering with more confidence — but these figures come from AR-menu vendors marketing
  their own product, so should be treated as an upper-bound estimate, not a guarantee,
  until validated independently.

### Recommended rollout approach (not yet built, but the natural next step)

Rather than 3D-scanning an entire menu upfront, a realistic path is: pick a restaurant's
2-3 highest-margin or most visually distinctive "hero dishes," get those professionally
scanned first (~$150-1,500 total), measure any real change in order patterns for those
specific items using the existing Menu Analytics feature, and expand only if the data
supports it. This keeps the upfront cost proportional to validated benefit rather than
speculative.

## Mixed Cart Splitting, and Getting Delivery Timing Right (Two Rounds of Fixes)

### Round 1 bug: cold drinks clogging the kitchen queue

When a customer's very first order mixed kitchen-made food (e.g. a pizza) with
an already-stocked instant item (e.g. bottled water), the entire cart used to be
dumped into a single order that always went to the Kitchen dashboard — meaning
an item that needs zero preparation sat in the same queue as real food, waiting
on a "wait time" it never needed.

### Round 2 bug (found via real testing, more subtle): "instant" delivery isn't
### always the RIGHT delivery, and the Round 1 fix over-corrected

Fixing Round 1 by delivering every non-kitchen item immediately created a NEW,
arguably worse problem: items like **ice cream or a cold drink** don't need
kitchen prep, but delivering them the instant they're ordered means they arrive
and then sit on the table for the entire kitchen wait time — an ice cream
melting for 20 minutes while the pizza cooks, or a cold drink going warm before
the food even shows up. "Doesn't need the kitchen" and "should be delivered
immediately" are two different questions that got incorrectly treated as one.

### The real fix: a per-item delivery timing choice

Every non-kitchen menu item now has an explicit **delivery timing** setting,
configurable by the owner in Admin (and shown clearly with a badge in the item
list):
- **"Right away"** — for items where early delivery has no downside (water,
  napkins, cutlery, condiments).
- **"Hold and deliver together with the food"** — for anything perishable or
  temperature-sensitive (cold drinks, ice cream, desserts) that would go warm,
  melt, or feel wrong served before the meal. These items are automatically
  attached to the SAME order as the kitchen items in that cart, so they are only
  delivered once the kitchen marks the food ready — arriving at the table at the
  same moment as the food, not before.
- **Fallback behavior**: if a "hold and deliver together" item is ordered with
  no kitchen items at all in the same cart (nothing to time it against), it
  safely falls back to immediate delivery rather than being held indefinitely.
- This distinction only applies to a customer's **initial** order. The "+1 More"
  mid-meal reorder flow deliberately does NOT hold items — if someone explicitly
  asks for another ice cream mid-meal, that's a standalone request made at a
  specific moment, and there's no new food order to time it against, so it's
  delivered right away regardless of the item's configured timing.

The demo menu seeded on every new signup includes both cases out of the box for
testing: **Iced Tea** and **Vanilla Ice Cream** are pre-configured as "hold and
deliver together," while **Water** is "deliver right away" — so the distinction
is demoable with zero setup.

**Tested and confirmed (both rounds):**
- A mixed cart (pizza + ice cream, both "hold with meal") correctly created a
  SINGLE order — confirmed the ice cream did NOT appear early on the Runner
  screen, and instead showed the exact same wait-time countdown as the pizza
  (tested with a 20-minute wait, matching the exact scenario that surfaced this
  bug) and only reached the Runner once the whole order was marked ready.
- A mixed cart (pizza + water, "deliver right away") correctly split into two
  orders — the pizza went to Kitchen only, the water appeared instantly on the
  Runner, confirming the immediate-delivery path still works correctly
  alongside the new hold logic.
- Both patterns tested simultaneously, on different tables, without interfering
  with each other.
- Edge case tested: ordering a "hold with meal" item completely alone (no food
  in the cart) correctly fell back to immediate delivery instead of being held
  forever with nothing to wait for.
- A kitchen-only cart and a plain instant-only cart both continued to work
  exactly as before, with no unnecessary extra orders created.
- The Admin toggle to flip an item between "deliver right away" and "hold for
  the meal" was tested and confirmed working, with the correct badge updating
  immediately.
- Menu Analytics re-verified to correctly count every item from every order
  type (kitchen, immediate, hold-for-meal, and mixed combinations) with no
  double-counting or missing items.

## Round 3 Fix: Delivery Timing Is a Customer Choice, Not Just an Owner Default

**The gap found after Round 2:** locking "hold and deliver with the meal" as a
fixed default per menu item assumed there's only ever one correct timing for a
given item. That's not true in practice — the same iced tea might be wanted
**immediately** by a couple who want a drink to sip while chatting and waiting
for their food, or **with the meal** by someone who wants it freshly poured
alongside their food. That's a preference that varies by customer and by
moment, not a fixed property of the menu item.

**The fix:** the restaurant owner's per-item setting ("Right away" vs. "Hold
and deliver together with the food") is now treated as a **default**, not a
hard rule. On the customer's menu page, any item configured as "hold with
meal" shows a small, explicit choice once it's added to the cart:
- **"⏱ Bring with my food"** (pre-selected, matches the owner's default)
- **"⚡ Bring it now"** (override, for exactly the "we want to talk before the
  food arrives" scenario)

This choice is sent per cart line, so a customer can order a pizza with one
drink they want immediately and another item they're happy to have arrive with
the food, all in the same order. If no explicit choice is sent at all (e.g. a
staff-assisted order placed through the "Take Order" screen, which doesn't yet
have this picker), the system correctly falls back to that menu item's own
configured default rather than guessing or erroring out.

**Tested and confirmed:**
- Ordered pizza + iced tea with the customer explicitly choosing "Bring it
  now" for the iced tea — confirmed the pizza went to the Kitchen alone and
  the iced tea was delivered to the Runner immediately, correctly overriding
  the item's own "with_meal" default.
- Ordered the same combination again with the customer explicitly keeping the
  default ("with_meal") — confirmed both items were correctly bundled into a
  single order, arriving together once the food was ready.
- Sent an order with no timing field specified at all — confirmed it correctly
  fell back to the menu item's own configured default ("with_meal" for iced
  tea), so older clients or the staff-assisted flow still behave sensibly.
- Confirmed the timing choice buttons appear on the customer menu ONLY for
  items actually configured as "with_meal," and correctly do NOT appear for
  "immediate" items (water) or kitchen-made items (pizza).
- Re-confirmed the "+1 More" mid-meal reorder flow is intentionally unaffected
  by this change — a standalone reorder request is always delivered right
  away regardless of the item's configured timing, since there's no new food
  order to time it against at that point.

## Accessibility: Customers Without Smartphones (Elderly Guests, etc.)

A real gap in a pure "QR-only" system: it excludes anyone without a smartphone — elderly
guests, a dead battery, someone who simply doesn't want to use a phone at a restaurant.
TableBell does **not** force every customer through self-service. It offers a proper
fallback that still gets the full benefit of the kitchen-bell system.

### The two-part fix

**1. Physical / no-technology fallback (for the table-tent card you print):**
Alongside the QR code, print a simple line like:
> *"No smartphone? No problem — just ask any staff member and they'll take your order for you."*

This costs nothing extra and requires no new technology — it just tells the customer
that human service is always available, exactly as it always has been.

**2. Digital fallback — the new "🙋 Take Order" screen (staff-only):**
When a customer asks a waiter to order for them, the waiter opens **"🙋 Take Order"**
(linked from Admin, Kitchen, and Runner navigation) — a simple staff-facing menu screen:
1. Select the table number
2. Enter their own name
3. Tap through the same menu to build the order exactly as the customer describes it
   verbally
4. Tap "Send to Kitchen"

**From that point on, the order flows through the exact same pipeline as any self-service
QR order** — same kitchen bell, same wait-time countdown logic, same runner delivery flow,
same analytics. The restaurant never loses the speed and labor benefits of the system just
because one table needs a human touch; it just needs one staff member available to key in
an order when asked, which is a completely normal part of hospitality anyway.

Kitchen dashboard cards for staff-placed orders show a small **"🙋 Taken by [name]"** tag
so the kitchen has context — informational only, doesn't change how the order is prepared.

### What's been tested

- ✅ Take Order screen loads the full live menu and all tables correctly
- ✅ A staff-placed order for a customer without a phone flows through the complete
  kitchen pipeline identically to a self-service order — confirmed prepare → ready →
  runner delivery all worked exactly the same way
- ✅ The staff member taking the order is automatically assigned as the responsible
  runner for that order (using the table's section assignment if one exists, or
  defaulting to whoever took the order)
- ✅ Confirmed via Analytics: a staff-placed item and a customer-placed item of the same
  menu item correctly merge into one combined total — an owner's sales reporting isn't
  split or distorted by how the order was entered
- ✅ Validation tested: rejects a staff-placed order with no staff name or no table
  selected
- ✅ Security tested: the Take Order screen and its API require the restaurant's staff to
  be logged in — a member of the public cannot place orders through this endpoint

## Payment System / Subscription Billing

TableBell now has a real subscription billing system built in, using Stripe's standard
integration pattern (Checkout + webhooks). It runs in one of two modes automatically:

- **Demo Mode** (default, no setup needed): if no `STRIPE_SECRET_KEY` environment variable
  is set, the app runs a fully simulated billing flow — subscribing, canceling, and even
  simulating a failed payment — with zero real charges and no payment provider account
  needed. This lets you test the entire billing lifecycle right now.
- **Live Mode**: once you set real Stripe API keys (see "Going Live" below), the exact
  same code paths switch to real Stripe Checkout sessions and real webhook-driven status
  updates — no code changes needed to flip the switch.

### How it works for a restaurant owner

1. **14-day free trial starts automatically at signup** — no card required. The Admin
   dashboard shows a countdown banner once the trial has 3 or fewer days left.
2. **Billing page** (`💳 Billing`, linked from every screen) shows current status (trial /
   active / past due / canceled), lets the owner subscribe or switch between the
   Starter/Growth/Pro plans, and shows a full payment history.
3. **If the trial expires without subscribing**, business/admin features (adding menu
   items, adding tables) get paused with a clear message and a "Choose a Plan" button —
   but existing Kitchen and Runner screens keep working for a short buffer period, so a
   restaurant mid-shift is never suddenly locked out.
4. **If a real payment fails** (expired card, insufficient funds, etc.), the account moves
   to "past due" with a **5-day grace period**. During this window, *everything keeps
   working normally* — Kitchen, Runner, and business features are all unaffected — while
   the owner sees a clear warning banner with a countdown to fix their payment method.
   This deliberately mirrors the "dunning" pattern from the original payment-recovery
   research: give the customer time to fix a routine card issue before anything breaks.
5. **Only if the grace period fully expires** (payment never fixed) do the
   service-critical Kitchen and Runner screens actually lock, redirecting to the Billing
   page. This is intentionally a last resort, not a first response, so a temporary card
   decline never interrupts an active dinner service.
6. **Canceling** a subscription (the owner's deliberate choice, not a failed charge) locks
   things down immediately rather than granting a grace period, since that's an
   intentional decision rather than an accident.

### What's been tested (in Demo Mode)

- ✅ Trial starts correctly at signup (confirmed 14 days shown on Billing page)
- ✅ Subscribing to a plan in demo mode instantly activates the account and records a
  Payment history entry with the correct plan and amount
- ✅ Simulating a failed payment correctly moves the account to "past due" and starts the
  grace-period countdown
- ✅ **Confirmed Kitchen and Runner screens remain fully accessible during the grace
  period** — tested by placing and completing a real order while the account was in
  "past due" status
- ✅ **Confirmed business features (adding a menu item) also remain accessible during the
  grace period** — a routine payment hiccup doesn't block daily operations
- ✅ Manually advanced a simulated failure to 6 days old (past the 5-day grace window) and
  confirmed Kitchen and Runner **correctly lock** at that point, redirecting to Billing
  with a clear message
- ✅ Simulating payment recovery correctly restores full access immediately
- ✅ Trial-expiry scenario tested separately: confirmed Kitchen still works within a
  2-day buffer past trial end, while business features (menu editing) correctly block
  and redirect to Billing
- ✅ Cancel flow tested and confirmed — correctly shows "Subscription Canceled" with a
  resubscribe option
- ✅ Multi-restaurant billing isolation tested and confirmed — each restaurant's trial
  status, subscription status, and payment history are completely separate

### Honest scope notes (what this does NOT do yet)

- **Not every single API endpoint is billing-gated** — the page views for `/kitchen` and
  `/runner` are gated (confirmed via testing above), and the main menu/table-adding
  endpoints are gated, but some underlying API calls used internally by those pages are
  not individually re-checked. In practice, since the page itself redirects away when
  billing is broken, a locked-out owner won't reach those API calls through normal usage
  — but this is worth hardening further before handling real customer money at scale.
- **Live Stripe integration is written but untested against a real Stripe account** in
  this environment (no live API keys are available here). The webhook handler, checkout
  session creation, and customer creation follow Stripe's standard, well-documented
  patterns, but you should test with Stripe's test-mode API keys before accepting real
  payments.
- **No proration handling** for mid-cycle plan switches yet — switching plans in live mode
  will follow Stripe's default behavior, which may need explicit configuration depending
  on how you want upgrades/downgrades billed.

### Going Live (switching from Demo Mode to real payments)

1. Create a Stripe account (or, per earlier research, Dodo Payments/Paddle if you're an
   India-based founder without direct Stripe access — they use a very similar
   integration shape).
2. In your Stripe Dashboard, create three recurring Products/Prices matching your plans
   ($99, $199, $349/month) and note their Price IDs.
3. Set these environment variables before running the app:
   - `STRIPE_SECRET_KEY` — your Stripe secret key
   - `STRIPE_PUBLISHABLE_KEY` — your Stripe publishable key
   - `STRIPE_WEBHOOK_SECRET` — from your webhook endpoint settings in Stripe
   - `STRIPE_PRICE_STARTER`, `STRIPE_PRICE_GROWTH`, `STRIPE_PRICE_PRO` — the three Price
     IDs from step 2
4. In Stripe, add a webhook endpoint pointing to `https://yourdomain.com/webhooks/stripe`
   listening for at least: `checkout.session.completed`, `invoice.payment_succeeded`,
   `invoice.payment_failed`, `customer.subscription.deleted`.
5. Test thoroughly with Stripe's test-mode card numbers before switching to live keys.

## What's Been Tested and Confirmed Working

- ✅ Restaurant signup/login with isolated data per restaurant (no restaurant can see
  another's orders/menu)
- ✅ Menu management: add, edit, enable/disable, delete items
- ✅ Table management with plan-based limits (Starter=10, Growth=25, Pro=unlimited)
- ✅ QR code generation for every table, linking directly to that table's order page
- ✅ Customer ordering: cart, quantities, per-item notes, order submission
- ✅ Kitchen dashboard: real-time polling (updates every 3 seconds), audible bell alert on
  new orders, wait-time setting, mark-ready action
- ✅ Customer's live countdown timer, correctly reflecting the wait time the cook sets
- ✅ Runner screen: shows only ready orders, oldest first, mark-delivered action
- ✅ **Smart refill routing**: instant items (water, fountain drinks) bypass the kitchen
  and alert the runner directly; kitchen-made items (pizza, fries, etc.) create a real
  order that goes through the full kitchen → wait-time → ready pipeline — tested and
  confirmed both paths work correctly and simultaneously without interfering with each
  other
- ✅ Per-item "needs kitchen prep" flag, settable and toggleable by the owner in Admin
- ✅ Non-item requests (napkins, assistance, check, custom notes): sent directly from the
  customer's phone to the runner screen; duplicate-request protection tested and
  confirmed; each restaurant's requests stay isolated from other restaurants (tested and
  confirmed)
- ✅ **Multi-waiter claiming system**: prevents duplicate trips when several waiters see
  the same alert. Tested with 5 simultaneous claim attempts on the same unclaimed
  request — confirmed exactly one succeeds and the other four are correctly rejected with
  the winning claimer's name. "Take Over" and "Release" actions tested and confirmed
  working. Per-device name is remembered locally with no login required.
- ✅ **Table Sections** (who should go when the bell rings): owner/staff can bulk-assign
  a whole group of tables to one runner in a single click (e.g. "Priya: tables 1-10"),
  reflecting that one runner covers far more tables than a traditional waiter once
  order-taking is removed. Tested at realistic scale (20 tables, 2 runners, 10 tables
  each, assigned in two bulk actions) — confirmed new requests and ready-orders for a
  table automatically show up as the correct runner's, with zero claiming needed;
  unassigned tables correctly fall back to the open claim system; "Cover For Them"
  correctly allows another runner to step in on an assigned table; "Unassign All" and
  "End of Shift" correctly clear assignments; security-tested to confirm one restaurant
  cannot view or modify another restaurant's table sections.
- ✅ Full order lifecycle: received → preparing → ready → delivered, reflected correctly
  on all three screens (kitchen, runner, customer) throughout
- ✅ Daily order count and revenue tracking on the admin dashboard
- ✅ **Menu analytics**: ranked best-sellers by quantity/orders/revenue, with refills of
  an item automatically merged into that item's totals; Today/Week/All-Time filters;
  "Never Ordered" flagging for items with zero sales in the period; quick top-5 widget on
  the main dashboard; verified fully isolated per restaurant
- ✅ **Subscription billing**: 14-day free trial, demo-mode simulated checkout/cancel,
  failed-payment grace period (5 days) during which Kitchen/Runner/business features all
  stay fully functional, hard-lock of Kitchen/Runner only after the grace period is
  genuinely exhausted, trial-expiry buffer for service-critical screens, full payment
  history log, and real Stripe Checkout + webhook integration code ready for live keys —
  see the dedicated "Payment System" section above for full test results and honest scope
  notes
- ✅ **Staff-assisted ordering** for customers without smartphones: a dedicated "Take
  Order" screen lets staff enter a verbal order on a customer's behalf, flowing through
  the identical kitchen-bell/wait-time/runner pipeline as self-service orders; confirmed
  order counts/revenue merge correctly with phone-placed orders in Analytics regardless
  of how the order was entered; validation and staff-login security tested
- ✅ **Augmented reality menu preview** (no app download, WebAR via AR Quick Look/Scene
  Viewer): owners can attach/edit/remove a 3D model per menu item; customers see a "View
  in 3D / AR" button that opens an interactive, rotatable preview and can launch native
  AR to place a life-size dish on their table; tested end-to-end with a real, working
  public 3D model (Khronos Group's glTF sample set) included by default on every new
  signup's demo menu; add/update/remove all confirmed working; restaurant-isolated same
  as other menu edits (confirmed a second restaurant cannot view or modify another's AR
  models). Full cost/scope honesty notes for populating a real menu with professional 3D
  models are documented separately above.
- ✅ **AR unlocked as a 3-month loyalty perk, not a day-one feature**: tested end-to-end
  that a brand-new signup cannot see or set AR models (confirmed both the Admin UI shows
  a locked message and the customer menu shows no AR button, even for an item with a
  model already attached behind the scenes); confirmed the "Demo: Unlock Now" tool
  correctly grants access and the AR button/controls immediately appear; confirmed
  "Demo: Reset Lock" correctly reverts to the locked state; **security-tested that the
  gate is enforced server-side** — a direct POST to the AR-update endpoint while locked
  is rejected and the item's data is left untouched, confirmed by inspecting the
  database directly, not just the rendered page.

---

## Technical Notes (for your understanding — no coding needed from you)

- Built with **Python/Flask** (a real, production-grade web framework — not a prototype
  tool) and a **SQLite database** (a real file-based database, `tablebell.db`, that stores
  all your restaurants, menus, tables, and orders)
- "Real-time" updates use **polling** — each screen automatically checks for updates every
  3 seconds. This is simple, reliable, and works well for this use case (a few seconds of
  delay is unnoticeable for restaurant orders)
- The kitchen "bell" sound is generated directly in the browser (no external sound file
  needed) — it will play automatically when a new order appears, and there's a
  "🔊 Test Sound" button to confirm your device's volume is working before service starts
- QR codes are generated using the `qrcode` Python library — no external API dependency,
  so QR generation works even without internet access to a third party

---

## What This Version Does NOT Yet Include (next steps)

- **Payment processing / subscription billing** — right now, choosing a plan just updates a
  setting; it does not charge a card. Adding real billing (via Dodo Payments or Stripe) is
  the next step once you're ready to charge real restaurants.
- **Hosting on the internet** — this currently runs on your own computer
  (`localhost:5050`), which only you can access. To let real restaurants and their
  customers use it, it needs to be deployed to a hosting service so it has a real public
  web address. I can help you do this next (there are simple, low-cost options like
  Render, Railway, or PythonAnywhere that don't require deep technical knowledge).
- **SMS/WhatsApp notifications** — currently all status updates happen on-screen; adding
  text message alerts is a possible future add-on.
- **Multi-language support, food photos, and advanced reporting** — nice-to-haves for
  later versions, not needed for your first real-world tests.

---

## Suggested Next Steps

1. **Run it locally and test it yourself** using the walkthrough above — place a few test
   orders, try it on your phone, get a feel for the whole flow.
2. **Get it hosted online** so you can show it to real restaurant owners without needing
   your own computer running — I can walk you through this.
3. **Add payment/subscription billing** once you're ready to start charging.
4. **Show it to your first real restaurant** for a free trial shift and gather feedback.
