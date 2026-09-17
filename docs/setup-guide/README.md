# Smart Marking Setup Guide

From an empty Railway account to students reading their feedback on a phone — every screen is the real app. About 20 minutes; no coding needed.

## 1. Before you start

You need three things: a **Railway account** (railway.com — the Hobby plan is enough for a school department), an **API key for one AI provider** that can read images, and about twenty minutes. Free keys that work: Google Gemini's free tier (aistudio.google.com/apikey) and OpenRouter's `:free` models. Paid options: TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot (Kimi) and Qwen.

Everything — scripts, marks, classes, your key — lives inside your own Railway project. Nothing is sent anywhere except the model calls you configure.

## 2. Deploy on Railway

Open [railway.com/deploy/smart-marking-1](https://railway.com/deploy/smart-marking-1) and click **Deploy Smart Marking**. Railway creates two services — `web` (the app) and `Postgres` (the database) — plus a small disk for page images. The first build takes two to three minutes.

Your sign-in password is generated for you. To read it: open the `web` service in Railway → **Variables** → `TEACHER_PASSWORD`. You can change it there at any time (the service restarts). To open the app, click the `web` service → **Settings** → **Networking** and follow the public domain (it looks like `web-production-xxxx.up.railway.app`).

![The template page on Railway. One click creates the app, the database and the storage.](images/00-railway-template.jpg)

*The template page on Railway. One click creates the app, the database and the storage.*

## 3. Sign in

Open the app's address and enter the teacher password from the step above. There is one shared teacher password per school deployment.

![The sign-in page. Teachers only — students never sign in.](images/01-sign-in.jpg)

*The sign-in page. Teachers only — students never sign in.*

## 4. Connect a model

Go to **Settings**. Pick a provider, paste its key, then click **Load models from provider** to see exactly which models your key can use. Choose a model marked *reads pages*, click **Test connection**, and **Save**.

Keys are kept per provider (a ✓ on the tile means a key is saved), so you can switch between providers without re-entering them. **Requests per minute** protects free keys with low rate limits — set it to 8 for TokenRouter's free model, 10 for Gemini's free tier.

![Settings: provider, model, key. Test connection makes one small text call and one image call.](images/02-settings.jpg)

*Settings: provider, model, key. Test connection makes one small text call and one image call.*

## 5. Create an assignment

Go to **Assignments → + New assignment**. Choose the type: *Maths / Science — mark scheme* for structured answers, *Essay — rubric* for open responses, or *Quick mark* for a short criteria list with no paper.

Give it a title, drop the **question paper** (PDF or photos) and click **Read questions** — the app transcribes every question and part into a table you can correct. Then drop the **mark scheme** and click **Read mark scheme**: each row shows the expected answer and its mark allocation (M1, A1, B1…). Add any notes the marker should know ("ECF applies", "accept any correct method"), check the tables, and **Save**.

Saved assignments go into a bank you can reuse across classes and years.

![The assignment editor after Read questions and Read mark scheme. Every cell is editable.](images/03b-assignment-editor-full.jpg)

*The assignment editor after Read questions and Read mark scheme. Every cell is editable.*

![The assignment bank.](images/04-assignments-bank.jpg)

*The assignment bank.*

## 6. Create a class and load the classlist

Go to **Classes → New class** and name it the way your school does ("4E2 Mathematics"). Every class gets a 4-character code — this one is `4KEF` — that students will type.

On the **Students** tab, upload a CSV with two columns, `name` and `reg_no` (register number). The preview flags duplicate or missing numbers before anything is saved; click **Confirm classlist** when it looks right.

Then click **Copy link** and paste it into Google Classroom (or wherever your students look). The link opens the app with the class code already filled in.

![Creating a class.](images/06-new-class.jpg)

*Creating a class.*

![CSV preview — issues are shown per row before you confirm.](images/08-classlist-preview.jpg)

*CSV preview — issues are shown per row before you confirm.*

![The classlist, the class code and the Copy link button.](images/09-classlist-loaded.jpg)

*The classlist, the class code and the Copy link button.*

## 7. Set the assignment for the class

On the class's **Assignments** tab click **Set assignment**, pick one from the bank, add a due date and click **Set for this class**. It starts as a *Draft*, invisible to students. Click **Open** when you want students to hand in.

![Setting an assignment from the bank.](images/10-set-assignment.jpg)

*Setting an assignment from the bank.*

![Opened — students can now see it.](images/11-class-assignments-open.jpg)

*Opened — students can now see it.*

## 8. Students hand in from their phones

A student opens the class link, types their register number and confirms their name. No account, no password: anyone with the class code and a number can see that student's work — the same trade-off as a paper script left on a desk.

**Hand in** takes photos with the camera or from the gallery. Pages can be re-ordered or deleted before handing in; photos are shrunk on the phone before upload, so it works on a weak signal. Up to 20 pages per script. Once handed in, the student sees a calm "Handed in" note — marking starts straight away in the background.

![Enter your number.](images/20-student-enter.jpg) 
![Confirm it's you.](images/21-student-confirm.jpg) 
![Home: what to hand in.](images/22-student-home.jpg) 
![Pages in order, ready to hand in.](images/24-student-hand-in-page.jpg) 
![Done.](images/25-student-handed-in.jpg) 
![Waiting for the teacher.](images/26-student-waiting.jpg) 

## 9. Marking, and the parts that need you

The assignment page shows the roster: who has handed in, what is being marked, and what is ready. You can also **Upload pages** for a student yourself (scanned booklets) and **Remove hand-in** so a student can redo it.

Each script is read by one model, marked against the scheme by a second pass, and checked by an independent reviewer. Anything illegible, not covered by the scheme, or where marker and reviewer disagree goes to **Review** with the reason. There you tick the allocations the student earned (or pick the band for an essay) and give a one-line reason — that reason feeds the nightly learning step, so the marker gets closer to your judgement over time.

Click a student's name to see the per-part marks, the transcription and the justification for each mark.

![The roster after marking: 1 ready, 0 needing you.](images/31-roster-marked.jpg)

*The roster after marking: 1 ready, 0 needing you.*

![A marked script, part by part.](images/32b-submission-detail-full.jpg)

*A marked script, part by part.*

## 10. Release feedback

Until you release, students see "Marked — your teacher is checking". **Release feedback** is one action for the whole class and needs every "Needs you" part cleared first. After release students see their total, a short summary, what they did well, each question with a comment and a "Try next", and what to work on.

Releasing closes student hand-ins for that assignment; pages you upload for a student later are still marked and shown automatically.

![The release confirmation.](images/34-release-dialog.jpg)

*The release confirmation.*

![What the student sees.](images/36-student-feedback.jpg) 
![A question expanded.](images/37-student-feedback-expanded.jpg) 

## 11. Marks and records

From the assignment page, **Download marks CSV** gives one row per student with a column per question part, and **Download marking records** gives a Word document per student — mark scheme row by row, the student's answer, the awarded mark and a blank "Teacher's mark" column for moderation — plus a markbook spreadsheet.

## 12. Good to know

**Student pages are deleted as soon as a script is done** (marked with nothing to check, or the last part resolved); the marking record keeps the transcription and every mark. Turn this off under Settings or per assignment if you want to keep the images.

**Cost.** A script needs about four model calls. On a paid provider that is typically well under one cent per script for a small model; on a free tier it is free within the daily limit.

**Changing the password or the secret.** The password is the `TEACHER_PASSWORD` variable on Railway. Leave `SECRET_KEY` alone — it encrypts the stored API keys; changing it means re-entering them.

**Updates.** Redeploying the `web` service picks up the latest version from GitHub; the database and stored keys are kept.

Source, issues and the full README: [github.com/twahidin/smart-marking-system](https://github.com/twahidin/smart-marking-system).
