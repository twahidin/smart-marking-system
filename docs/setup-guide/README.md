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

**My models.** OpenRouter and TokenRouter host hundreds of models beyond the curated list. Under those two providers a *My models* list lets you add any model id (with a label and whether it reads pages); it then appears in every model picker, here and in the assignment editor. Each id returned by *Load models from provider* gets a **+ Add** button.

![Settings: provider, model, key. Test connection makes one small text call and one image call.](images/02-settings.jpg)

*Settings: provider, model, key. Test connection makes one small text call and one image call.*

![My models: your own OpenRouter or TokenRouter model ids, available everywhere a model is picked.](images/40-my-models.jpg)

*My models: your own OpenRouter or TokenRouter model ids, available everywhere a model is picked.*

## 5. Create an assignment

Go to **Assignments → + New assignment**. Choose the type: *Maths / Science — mark scheme* for structured answers, *Essay — rubric* for open responses, or *Quick mark* for a short criteria list with no paper.

Give it a title, drop the **question paper** (PDF or photos) and click **Read questions** — the app transcribes every question and part into a table you can correct. Then drop the **mark scheme** and click **Read mark scheme**: each row shows the expected answer and its mark allocation (M1, A1, B1…). Add any notes the marker should know ("ECF applies", "accept any correct method"), check the tables, and **Save**.

Saved assignments go into a bank you can reuse across classes and years.

**Subjects.** Maths, English and Science as before, plus **MT** (Mother Tongue — pick Chinese, Malay or Tamil; the script is read in that language and the student's feedback is written in it, while everything you see stays in English) and **Computing**, whose students can hand in program files as well as photos.

![The assignment editor after Read questions and Read mark scheme. Every cell is editable.](images/03b-assignment-editor-full.jpg)

*The assignment editor after Read questions and Read mark scheme. Every cell is editable.*

![The assignment bank.](images/04-assignments-bank.jpg)

*The assignment bank.*

![A Computing assignment: students may hand in .py, .sb3 and .xlsx files.](images/50-editor-computing.jpg)

*A Computing assignment: students may hand in .py, .sb3 and .xlsx files.*

![An MT assignment names its language.](images/51-editor-mt-language.jpg)

*An MT assignment names its language.*

## 6. Choose the model per assignment

Every assignment follows Settings by default (*Auto — follow Settings*): change the model in Settings and every assignment changes with it. For one assignment that deserves something different — a hard paper for a stronger model, a quick quiz for a cheap one — open it, go to **Model** and pick *Choose a model*. Only providers with a saved key can be selected; choose the model, optionally a different one for reading pages, and **Save**. The assignment bank shows the choice as a small caption.

Removing a provider's key while assignments still use it asks you to confirm first — those assignments would fail to mark until you point them at another model.

**A default per subject.** Under **Settings → By subject** you can give each subject its own default — a model that reads Chinese, Malay or Tamil handwriting well for MT, one that is strong at code for Computing — and new assignments in that subject follow it. The order is always: the assignment's own choice, then its subject's default, then Settings.

![The Model section of an assignment: Auto, or a provider and model of your own.](images/41-assignment-model.jpg)

*The Model section of an assignment: Auto, or a provider and model of your own.*

![Settings → By subject: one default model per subject, Auto by default.](images/52-settings-by-subject.jpg)

*Settings → By subject: one default model per subject, Auto by default.*

## 7. Create a class and load the classlist

Go to **Classes → New class** and name it the way your school does ("4E2 Mathematics"). Every class gets a 4-character code — this one is `4KEF` — that students will type.

On the **Students** tab, upload a CSV with two columns, `name` and `reg_no` (register number). The preview flags duplicate or missing numbers before anything is saved; click **Confirm classlist** when it looks right.

Then click **Copy link** and paste it into Google Classroom (or wherever your students look). The link opens the app with the class code already filled in.

![Creating a class.](images/06-new-class.jpg)

*Creating a class.*

![CSV preview — issues are shown per row before you confirm.](images/08-classlist-preview.jpg)

*CSV preview — issues are shown per row before you confirm.*

![The classlist, the class code and the Copy link button.](images/09-classlist-loaded.jpg)

*The classlist, the class code and the Copy link button.*

## 8. Set the assignment for the class

On the class's **Assignments** tab click **Set assignment**, pick one from the bank, add a due date and click **Set for this class**. It starts as a *Draft*, invisible to students. Click **Open** when you want students to hand in.

![Setting an assignment from the bank.](images/10-set-assignment.jpg)

*Setting an assignment from the bank.*

![Opened — students can now see it.](images/11-class-assignments-open.jpg)

*Opened — students can now see it.*

## 9. Students hand in from their phones

A student opens the class link, types their register number and confirms their name. No account, no password: anyone with the class code and a number can see that student's work — the same trade-off as a paper script left on a desk.

**Hand in** takes photos with the camera or from the gallery. Pages can be re-ordered or deleted before handing in; photos are shrunk on the phone before upload, so it works on a weak signal. Up to 20 pages per script. Once handed in, the student sees a calm "Handed in" note — marking starts straight away in the background.

![Enter your number.](images/20-student-enter.jpg) 
![Confirm it's you.](images/21-student-confirm.jpg) 
![Home: what to hand in.](images/22-student-home.jpg) 
![Pages in order, ready to hand in.](images/24-student-hand-in-page.jpg) 
![Done.](images/25-student-handed-in.jpg) 
![Waiting for the teacher.](images/26-student-waiting.jpg) 

## 10. Computing: hand in files, not just photos

For a Computing assignment the hand-in page has a third button, **Add files**: Python (`.py`), Scratch (`.sb3`) and Excel (`.xlsx`) files, or a `.zip` of them, alone or together with photos of anything written on paper — up to 20 items and 12 files per hand-in, 2 MB per file. Teachers can drop the same files for a student from the class page.

The app *reads* the work; it never runs it. Python is shown with line numbers and a syntax check, Scratch projects as their blocks in words (*when green flag clicked · repeat (10) · move (10) steps*), and spreadsheets cell by cell with the formula and its value. The marker cites the file and line for every mark, and the submission page keeps that text even after the files are deleted.

![A marked Python file: the rendered text, the marks with their citations, and the feedback.](images/55-submission-detail-files.jpg)

*A marked Python file: the rendered text, the marks with their citations, and the feedback.*

![Add files sits next to the camera buttons.](images/54-student-hand-in-files.jpg) 

## 11. Bulk upload a whole class

Instead of uploading student by student, put the whole class's work in one `.zip` where each file or folder starts with the register number — `07_amirah.py`, `07/…`, `7 - amirah/` — and click **Bulk upload** on the class assignment page. The preview shows who was matched, which files were skipped and what could not be matched, before anything is saved.

Students who have already handed in are skipped unless you tick **Replace existing hand-ins**. Photos in a bulk zip are not shrunk in the browser, so keep the zip under 50 MB unpacked or split the class in two.

![The bulk-upload preview: matched students, skipped files, unmatched entries.](images/53-bulk-upload-preview.jpg)

*The bulk-upload preview: matched students, skipped files, unmatched entries.*

## 12. Marking, and the parts that need you

The assignment page shows the roster: who has handed in, what is being marked, and what is ready. You can also **Upload pages** for a student yourself (scanned booklets) and **Remove hand-in** so a student can redo it.

Each script is read by one model, marked against the scheme by a second pass, and checked by an independent reviewer. Anything illegible, not covered by the scheme, or where marker and reviewer disagree goes to **Review** with the reason. There you tick the allocations the student earned (or pick the band for an essay) and give a one-line reason — that reason feeds the nightly learning step, so the marker gets closer to your judgement over time.

Click a student's name to see the per-part marks, the transcription and the justification for each mark.

**An error costs marks once.** If the same slip would lose marks in two places, the reviewer flags it and the app keeps the deduction where it first happened, restoring the later one — or sends it to Review as *double penalty* when it cannot tell which allocation to restore.

![The roster after marking: 1 ready, 0 needing you.](images/31-roster-marked.jpg)

*The roster after marking: 1 ready, 0 needing you.*

![A marked script, part by part.](images/32b-submission-detail-full.jpg)

*A marked script, part by part.*

## 13. Release feedback

Until you release, students see "Marked — your teacher is checking". **Release feedback** is one action for the whole class and needs every "Needs you" part cleared first. After release students see their total, a short summary, what they did well, each question with a comment and a "Try next", and what to work on.

Releasing closes student hand-ins for that assignment; pages you upload for a student later are still marked and shown automatically.

![The release confirmation.](images/34-release-dialog.jpg)

*The release confirmation.*

![What the student sees.](images/36-student-feedback.jpg) 
![A question expanded.](images/37-student-feedback-expanded.jpg) 

## 14. Insights: where the class lost marks

Once the first script is marked, the assignment's **Insights** tab shows the class as a whole: marks by part with the weakest highlighted, the allocations most often lost, a score distribution, and which students are struggling on which parts.

When the whole set has been marked, and again when you release, the app asks the model for a short narrative written for you, not for students — a summary, strengths, gaps and recommended next steps. Student names never reach the model: it sees register numbers and the app joins the names back. **Regenerate** refreshes the narrative after more scripts come in; **Download PDF** gives a one-file report for a department meeting.

![The Insights tab: numbers first, then the narrative and the students to support.](images/42-insights.jpg)

*The Insights tab: numbers first, then the narrative and the students to support.*

## 15. Telegram notifications (optional)

Get a message when scripts come in and when marking finishes, plus a daily report. In Telegram, message **@BotFather**, send `/newbot`, and copy the token it gives you. In **Settings → Notifications** paste the token and **Save**, then open your new bot in Telegram and press **Start** — within a few seconds the status changes to *Linked ✓*. **Test connection** sends a test message.

You get an instant message for new hand-ins (batched) and one when a class set finishes marking, each with links back to the app. The daily report arrives at the time you set — 07:00 Singapore time by default — and only on days something happened. Turn instant messages off to keep just the daily report. One chat per deployment: a department group works well — add the bot to the group and press `/start` there.

![Settings → Notifications: token, link status, instant messages, daily report time and time zone.](images/43-notifications.jpg)

*Settings → Notifications: token, link status, instant messages, daily report time and time zone.*

## 16. Marks and records

From the assignment page, **Download marks CSV** gives one row per student with a column per question part, and **Download marking records** gives a Word document per student — mark scheme row by row, the student's answer, the awarded mark and a blank "Teacher's mark" column for moderation — plus a markbook spreadsheet.

## 17. Good to know

**Student pages are deleted as soon as a script is done** (marked with nothing to check, or the last part resolved); the marking record keeps the transcription and every mark. Turn this off under Settings or per assignment if you want to keep the images.

**Cost.** A script needs about four model calls. On a paid provider that is typically well under one cent per script for a small model; on a free tier it is free within the daily limit.

**Changing the password or the secret.** The password is the `TEACHER_PASSWORD` variable on Railway. Leave `SECRET_KEY` alone — it encrypts the stored API keys; changing it means re-entering them.

**File limits.** 12 files per submission, 2 MB per program file, 20 MB per zip and 50 MB per upload; `.xlsm` and macros are refused, and nothing you upload is ever executed.

**Telegram and Insights are optional.** Nothing is sent to Telegram until you link a bot, and Insights only use the model you already configured — no extra keys.

**Updates.** Redeploying the `web` service picks up the latest version from GitHub; the database and stored keys are kept.

Source, issues and the full README: [github.com/twahidin/smart-marking-system](https://github.com/twahidin/smart-marking-system).
