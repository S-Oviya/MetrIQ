# METRA — TEAM DEVELOPMENT README

## SIH26035 — NAWI Test Report Generation Software

**Project:** METRA
**Full Name:** Metrology Test & Regulatory Application
**Problem Statement:** SIH26035
**Team Size:** 6
**Development Method:** GitHub + ChatGPT + Antigravity

---

# 1. WHAT THIS README IS FOR

This README is for all 6 team members.
PERSON 1-OVIYA
PERSON 2-YOGESH 
PERSON 3)SUSHA
PERSON 4)RACHITHA
PERSON 5)SWETHA
PERSON 6) SHINY

 WORK FOR TODAY AND TOMMORROW:

TODAY
Person	Work
P1	 WORK IS OVER
P2	 Regulatory Engine
P3	 Instruments + Jobs
P4	 Test Engine + Calculations
P5   NOTHING FOR TODAY
P6	 Reports + Dashboard
TOMORROW
Person	Work
P1	Core integration + connect everyone
P2	Regulatory → Instrument/Test integration
P3	Instrument/Job → Test integration
P4	Test → Calculation → PASS/FAIL integration
P5	Evidence + Workflow + Review
P6	Reports → approved results + Archive

 
The workflow is:

```text
GitHub Repository
       ↓
Clone Repository
       ↓
Find Project Folder Location
       ↓
Install / Open Antigravity
       ↓
Open Team ChatGPT Link
       ↓
Tell ChatGPT your Person Number + Project Location
       ↓
Get ONE Antigravity Prompt
       ↓
Paste Prompt into Antigravity
       ↓
Allow Required Actions
       ↓
Antigravity Works on Project
       ↓
Paste Antigravity Output into ChatGPT
       ↓
Get Next Prompt
       ↓
Repeat
       ↓
Inspect Your Work
       ↓
Commit
       ↓
Push Your Branch
       ↓
Person 1 Integrates Everything
```

## VERY IMPORTANT

**You do NOT need to manually open the project folder inside Antigravity.**

Instead, the **project location is written inside the Antigravity prompt**.

---

# 2. OUR DEVELOPMENT TREE

```text
                           METRA
                             │
                     PERSON 1 — TL
                           10%
                  CORE + INTEGRATION
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
      PERSON 2           PERSON 3           PERSON 4
        20%                20%                 20%
    REGULATORY         INSTRUMENTS +       TEST ENGINE +
       ENGINE                JOBS           CALCULATIONS
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
                        PERSON 5
                          20%
                  WORKFLOW + EVIDENCE
                             │
                             ▼
                        PERSON 6
                          10%
                  REPORTS + DASHBOARD
```

---

# 3. PERSON 1 — TEAM LEAD — 10%

## Main responsibility

**Core architecture + integration + final system**

Person 1 coordinates the complete application.

### Work

```text
Project Architecture
Database Foundation
API Structure
Shared Types
Authentication Foundation
Roles / Permissions
Global Routing
Shared Components
Environment Configuration
Integration
Deployment
Final Testing
```

### Main ownership

```text
src/
├── app/
├── routes/
├── types/
├── services/api/
└── config/

backend/
├── app/main.py
├── api/router.py
├── core/
├── database/
└── shared/
```

### Person 1 is also responsible for

* Integrating everyone's branches.
* Resolving integration conflicts.
* Running the final end-to-end test.
* Making sure the final application works as one system.

---

# 4. PERSON 2 — REGULATORY ENGINE — 20%

## Main responsibility

Build the regulatory and metrology logic.

### Work

```text
Legal Metrology Rules
OIML R76 Data
NAWI Accuracy Classes
Max / Min
e / d / n
MPE Tables
Regulatory Versions
Amendments
Applicability Rules
Test Applicability
Test Plan Generation
```

### Main folders

```text
frontend/src/modules/regulatory/

backend/app/regulatory/
```

### Important

Person 2 owns the regulatory rules.

Person 4 consumes these rules for calculations.

**Do not duplicate regulatory tables inside the Test Engine.**

---

# 5. PERSON 3 — INSTRUMENTS + JOBS — 20%

## Main responsibility

Manage weighing instruments and test jobs.

### Instrument data

```text
Manufacturer
Model
Serial Number
Accuracy Class
Max
Min
e
d
n
Instrument Type
Zero Setting
Tare
Multi-range
Multi-interval
Electronic
Software
Model Approval
```

### Job types

```text
MODEL_APPROVAL
INITIAL_VERIFICATION
RE_VERIFICATION
POST_REPAIR
POST_RELOCATION
RETEST
```

### Main folders

```text
frontend/src/modules/instruments/
frontend/src/modules/jobs/

backend/app/instruments/
backend/app/jobs/
```

### Dependency

Person 3 creates the instrument and job.

Person 2 provides the regulatory profile.

Person 4 executes the applicable tests.

---

# 6. PERSON 4 — TEST ENGINE + CALCULATIONS — 20%

## Main responsibility

Build test execution and calculation functionality.

### Tests

```text
Weighing Performance
Eccentricity
Repeatability
Zero Return
Creep
Digital Discrimination
Tare
Temperature Effect
Construction Examination
Software Examination
```

### Calculation modules

```text
backend/app/calculations/

├── mpe.py
├── weighing.py
├── eccentricity.py
├── repeatability.py
├── zero_return.py
├── creep.py
├── discrimination.py
├── tare.py
└── temperature.py
```

### Generic structure

```text
Test Definition
      ↓
Test Run
      ↓
Raw Observations
      ↓
Calculation
      ↓
PASS / FAIL
```

### Important

Person 4 gets regulatory limits from Person 2.

Do not create a second regulatory engine.

---

# 7. PERSON 5 — WORKFLOW + EVIDENCE — 20%

## Main responsibility

Make the test process traceable and reviewable.

### Equipment

```text
Equipment ID
Reference / Test Weight
Nominal Mass
Accuracy Class
Certificate
Calibration Date
Expiry
Traceability
```

### Environment

```text
Temperature
Humidity
Pressure
Voltage
Frequency
Start Time
End Time
```

### Evidence

```text
Photos
Certificates
External Reports
Documents
Remarks
Attachments
```

### Workflow

```text
Tester
   ↓
Execute Tests
   ↓
Submit
   ↓
Reviewer
   ↓
Approve
   ↓
Report
```

### Failure / Retest

Never overwrite a failed test.

Example:

```text
Test Run #1
     ↓
   FAILED
     ↓
Reason Recorded
     ↓
Correction
     ↓
Test Run #2
     ↓
    PASS
```

Both test runs should remain available.

### Audit trail

Record:

```text
User
Action
Timestamp
Old Value
New Value
Reason
```

### Main folders

```text
frontend/src/modules/equipment/
frontend/src/modules/evidence/
frontend/src/modules/workflow/
frontend/src/modules/audit/

backend/app/equipment/
backend/app/evidence/
backend/app/workflow/
backend/app/audit/
```

---

# 8. PERSON 6 — REPORTS + DASHBOARD — 10%

## Main responsibility

Generate reports and provide the final dashboard/archive experience.

### Reports

```text
OIML R76-2:2007 Type Evaluation Report
GATC Third Schedule Verification Certificate
Generic / State-Configurable Verification Certificate
Rejection Document
Technical Evidence Annex
```

### Dashboard

```text
Active Jobs
Pending Reviews
Failed Tests
Retests
Completed Jobs
Recent Reports
```

### Archive

Search by:

```text
Serial Number
Instrument ID
Job ID
Report Number
Approval Number
Date
```

### Main folders

```text
frontend/src/modules/dashboard/
frontend/src/modules/reports/
frontend/src/modules/archive/

backend/app/reports/
```

---

# 9. BEFORE STARTING — REQUIRED DOWNLOADS

Before cloning the METRA repository, every team member should have the following installed or available.

## REQUIRED

### 1. Git

Git is required to:

```text
Clone the repository
Create branches
Commit changes
Push your work
Pull updates
```

Check if Git is installed:

```bash
git --version
```

If you see something like:

```text
git version 2.x.x
```

Git is ready.

If Git is not recognized, install **Git for Windows** before continuing.

---

### 2. Node.js + npm

Node.js is required for the METRA frontend.

npm is installed automatically with Node.js.

Check:

```bash
node --version
```

Then:

```bash
npm --version
```

If both commands return version numbers, Node.js and npm are ready.

Use a current **LTS version of Node.js**.

---

### 3. Python

Python is required for the METRA backend.

Check:

```bash
python --version
```

If that does not work on your computer, try:

```bash
py --version
```

If either command returns a Python version, Python is ready.

---

### 4. Antigravity

Antigravity is the main AI development tool used by the team.

Install and sign in to Antigravity before starting your assigned work.

You will use it to:

```text
Inspect the project
Create files
Modify code
Run commands
Run tests
Implement your assigned module
```

**You do NOT need to manually open the METRA project folder inside Antigravity.**

The exact project location will be included inside the prompts generated by ChatGPT.

---

### 5. ChatGPT

ChatGPT is used as the team's development coordinator.

You need access to the **Team METRA ChatGPT conversation** provided by Person 1.

ChatGPT will provide:

```text
Development guidance
Architecture context
Regulatory context
Antigravity prompts
Git guidance
Debugging guidance
Integration guidance
```

---

### 6. GitHub Account

You need a GitHub account with access to the METRA repository.

Repository:

```text
https://github.com/S-Oviya/MetrIQ.git
```

Person 1 will make sure the required team members have the appropriate repository access.

---

### 7. Web Browser

Keep a modern browser installed, preferably:

```text
Google Chrome
Microsoft Edge
Mozilla Firefox
```

A browser will be useful for:

```text
Running the METRA frontend
Testing the application
Checking GitHub
Using ChatGPT
Using Antigravity
```

---

# 10. CHECK YOUR INSTALLATION BEFORE CLONING

Open **Command Prompt** and run these commands one at a time:

```bash
git --version
```

```bash
node --version
```

```bash
npm --version
```

```bash
python --version
```

If `python --version` does not work, try:

```bash
py --version
```

You should get version numbers for the installed tools.

Example:

```text
git version 2.x.x
v22.x.x
10.x.x
Python 3.x.x
```

The exact version numbers may be different.

---

# 11. WHAT YOU DO NOT NEED TO INSTALL YET

You do **not** need to install additional development software just because you are joining the team.

In particular, you do not need:

```text
VS Code
Android Studio
Docker
Postman
Ollama
A local AI model
```

unless Person 1 / ChatGPT specifically asks you to install something for your assigned task.

The main required setup is:

```text
Git
Node.js + npm
Python
Antigravity
ChatGPT
GitHub access
Web Browser
```

---

# 12. STEP 1 — INSTALL / CHECK GIT

Open **Command Prompt**.

Run:

```bash
git --version
```

If you see something like:

```text
git version 2.x.x
```

Git is installed.

If Git is not recognized, install Git before continuing.

---

# 13. STEP 2 — CLONE THE REPOSITORY

The Team Lead will send the GitHub repository link.

The current METRA repository is:

```text
https://github.com/S-Oviya/MetrIQ.git
```

Open Command Prompt where you want the project to be stored.

Then run:

```bash
git clone https://github.com/S-Oviya/MetrIQ.git
```

Then enter the project:

```bash
cd MetrIQ
```

---

# 14. STEP 3 — FIND THE EXACT PROJECT LOCATION

This is VERY important.

The Antigravity prompts need the exact project folder location.

Inside Command Prompt, while inside the project folder, run:

```bash
cd
```

You should get something similar to:

```text
C:\Users\YourName\Desktop\MetrIQ
```

That is your **PROJECT LOCATION**.

Copy it.

---

# 15. IF YOU DON'T KNOW HOW TO FIND THE LOCATION

Ask ChatGPT.

Use:

I am on Windows.

I cloned the METRA GitHub repository, but I don't know the exact location of the cloned project folder.

Give me the simplest Command Prompt command to find the current folder location.

I am a beginner, so give me only the easiest method.

---

# 16. STEP 4 — INSTALL / OPEN ANTIGRAVITY

Make sure Antigravity is installed.

Open Antigravity.

## IMPORTANT

**Do not worry about manually opening the cloned project folder inside Antigravity.**

The project location will be given to Antigravity through the prompt.

---

# 17. STEP 5 — OPEN THE TEAM CHATGPT LINK

The Team Lead will send you a ChatGPT conversation containing the complete METRA project context.

It contains:

```text
Problem Statement
Project Architecture
Regulatory Knowledge
Development Tree
Team Responsibilities
Technical Decisions
Integration Rules
```

Use this conversation as the project's coordination point.

---

# 18. STEP 6 — TELL CHATGPT WHO YOU ARE

Your first message should contain:

```text
PERSON NUMBER
PROJECT LOCATION
READINESS TO START
```

For example:

I am PERSON 2.

I have already cloned the METRA GitHub repository.

My exact project folder location is:

C:\Users\YourName\Desktop\MetrIQ

I have Antigravity installed.

I am ready to start my assigned work.

Give me the FIRST SINGLE Antigravity prompt I should paste into Antigravity.

IMPORTANT:
I will NOT manually open the project folder in Antigravity.

The Antigravity prompt must explicitly tell Antigravity to work with the project at the exact location I provided above.

Do not give me multiple prompts.

After Antigravity finishes, I will paste its output here and you will give me the next prompt.

---

# 19. WHAT CHATGPT WILL DO

ChatGPT will generate an Antigravity prompt.

The prompt should contain your project location.

Example:

```text
You are working on the METRA SIH26035 project.

PROJECT LOCATION:
C:\Users\YourName\Desktop\MetrIQ

You are PERSON 2 — Regulatory Engine.

Work directly with the project at the above location.

First inspect the existing project structure relevant to your assigned work.

...

[Task]
```

Copy the complete prompt.

---

# 20. STEP 7 — PASTE THE PROMPT INTO ANTIGRAVITY

Paste ChatGPT's prompt into Antigravity.

Antigravity will work with the project at the location specified in the prompt.

You do not need to manually browse to the project folder first.

---

# 21. STEP 8 — ALLOW ANTIGRAVITY'S ACTIONS

Antigravity may ask permission to:

```text
Create files
Modify files
Run terminal commands
Install packages
Run tests
Execute scripts
```

If the action is clearly required for the current task:

**Allow it.**

If Antigravity asks to do something unexpected or unrelated:

**Stop and ask ChatGPT first.**

---

# 22. STEP 9 — WAIT FOR ANTIGRAVITY TO FINISH

When Antigravity finishes, it may provide a summary such as:

```text
Implemented...
Created...
Modified...
Tests passed...
```

Copy the relevant output.

---

# 23. STEP 10 — PASTE ANTIGRAVITY'S OUTPUT INTO CHATGPT

Use:

Antigravity finished the previous task.

Here is the complete output:

[PASTE ANTIGRAVITY OUTPUT HERE]

I am still working on the same project.

Give me the NEXT SINGLE Antigravity prompt.

Do not give me multiple prompts.

Do not restart or redesign completed work.

---

# 24. REPEAT THIS LOOP

```text
ChatGPT
   ↓
ONE Antigravity Prompt
   ↓
Antigravity
   ↓
Implementation
   ↓
Antigravity Output
   ↓
ChatGPT
   ↓
NEXT Prompt
```

Repeat until ChatGPT says your assigned work is complete.

---

# 25. NEVER ASK FOR ALL PROMPTS AT ONCE

### Do NOT say:

```text
Give me all the prompts for my entire module.
```

### Say:

```text
Give me the NEXT SINGLE Antigravity prompt.
```

This is important because the next prompt should depend on what Antigravity actually found and implemented.

---

# 26. IF ANTIGRAVITY REACHES ITS FREE LIMIT

If your Antigravity usage/credit limit is reached:

## DO NOT:

```text
Delete the project
Clone again
Start over
Delete your work
Reset the repository
```

Your code is already saved locally.

---

# 27. SWITCHING TO ANOTHER ANTIGRAVITY ACCOUNT

If you have another authorized account available:

```text
Current Antigravity account
        ↓
Usage limit reached
        ↓
Switch to another authorized account
        ↓
Use the SAME computer/project
        ↓
Continue from existing code
```

Use your own/authorized Gmail account.

Do not use fake identities or attempt to bypass platform restrictions.

---

# 28. AFTER SWITCHING ANTIGRAVITY ACCOUNT

Tell ChatGPT:

My previous Antigravity account reached its usage limit.

I have switched to another authorized Antigravity account.

The local METRA project is still in the same location:

C:\Users\YourName\Desktop\MetrIQ

The existing code must be preserved.

Do NOT restart the implementation.

Give me a prompt for Antigravity to continue from the current project state.

---

# 29. IF YOUR CURRENT ANTIGRAVITY MODEL/CREDITS RUN OUT

If the Antigravity model selector provides another available model, such as Claude Sonnet, you can switch to an available model.

Example:

```text
Antigravity model
       ↓
Current model limit reached
       ↓
Select available Claude model
       ↓
Continue using existing project
```

The code does not disappear when you change models.

---

# 30. AFTER SWITCHING MODELS — INSPECT FIRST

Do NOT immediately ask the new model to continue coding.

First inspect what has already been done.

Ask ChatGPT for a prompt similar to:

```text
Inspect the current METRA project at:

C:\Users\YourName\Desktop\MetrIQ

I am PERSON X.

A previous Antigravity model/account was working on my assigned module.

Do NOT modify code yet.

Inspect and report:

1. Files created
2. Files modified
3. Features completed
4. Features partially completed
5. Errors
6. Failed tests
7. Remaining work
8. Integration issues

Do not rewrite existing working code.
```

Paste that into Antigravity.

Then paste the inspection output into ChatGPT.

ChatGPT will decide the next implementation prompt.

---

# 31. IMPORTANT — NEW ACCOUNT DOES NOT MEAN NEW PROJECT

Always remember:

```text
Antigravity Account
        ≠
Project
```

and:

```text
ChatGPT Conversation
        ≠
Project
```

The actual project is the code stored on your computer.

Therefore:

```text
Account changes → Code stays
Model changes → Code stays
Chat changes → Code stays
Computer restart → Code stays
```

---

# 32. IF CHATGPT'S CONVERSATION BECOMES TOO LONG

If ChatGPT reaches  limit i want you to like branch the last msg and then continue


# 35. WHEN CHATGPT SAYS YOUR WORK IS COMPLETE

Do not immediately push.

First inspect the code.

Ask ChatGPT for a final inspection prompt.

The inspection should check:

```text
Functionality
TypeScript errors
Python errors
Imports
API connections
Database integration
Edge cases
UI issues
Missing files
Integration
Unnecessary duplicate code
Accidental changes outside module
```

---

# 36. FINAL INSPECTION PROMPT

Use ChatGPT to generate a prompt similar to:

```text
Inspect my completed METRA module at:

C:\Users\YourName\Desktop\MetrIQ

I am PERSON X.

This is my assigned module.

Do NOT rewrite working code.

Thoroughly inspect:

- functionality
- errors
- imports
- API integration
- database integration
- edge cases
- UI
- integration with the rest of METRA
- accidental changes outside my ownership

Run appropriate tests/checks where available.

Fix only genuine issues.

At the end, clearly report:
1. What was checked
2. What was fixed
3. What remains
4. Whether my module is ready to commit
```

---

# 37. BEFORE GIT — CHECK YOUR CHANGES

Open Command Prompt.

Make sure you are inside your project folder.

Run:

```bash
git status
```

This shows changed files.

---

# 38. CHECK THAT YOU DIDN'T MODIFY SOMEONE ELSE'S MODULE

Example:

You are Person 2.

Expected:

```text
frontend/src/modules/regulatory/
backend/app/regulatory/
```

If you suddenly see changes in:

```text
reports/
dashboard/
equipment/
workflow/
```

STOP.

Ask ChatGPT or Person 1 before committing.

---

# 39. YOUR BRANCHES

Recommended branches:

```text
Person 1 → feature/core-integration

Person 2 → feature/regulatory

Person 3 → feature/instruments-jobs

Person 4 → feature/test-engine

Person 5 → feature/workflow-evidence

Person 6 → feature/reports-ui
```

---

# 40. CREATE YOUR BRANCH

If your branch has not already been created:

Example for Person 2:

```bash
git checkout -b feature/regulatory
```

Check:

```bash
git branch
```

You should see:

```text
* feature/regulatory
  main
```

The `*` shows your current branch.

---

# 41. COMMIT YOUR WORK

First:

```bash
git status
```

If you have verified the changes belong to your work:

```bash
git add .
```

Then:

```bash
git commit -m "Implement regulatory engine"
```

Use a commit message describing your actual work.

---

# 42. PUSH YOUR BRANCH

Example:

```bash
git push -u origin feature/regulatory
```

Use your own branch name.

---

# 43. IF YOU DON'T KNOW THE GIT COMMAND

DO NOT GUESS.

Ask ChatGPT.

Give it:

```text
git status
```

output.

Use:

I am PERSON X working on METRA SIH26035.

I am at the Git stage.

Here is my current git status:

[PASTE OUTPUT]

I need to [create my branch / commit / push / fix an error].

Give me the exact Command Prompt commands in the correct order.

I am a beginner.

Do not give me unnecessary commands.

---

# 44. IF GIT SHOWS AN ERROR

Copy the complete error.

Send it to ChatGPT.

Use:

I am PERSON X working on METRA SIH26035.

I received this Git error:

[PASTE COMPLETE ERROR]

My current branch is:

[BRANCH NAME]

Tell me what the error means and give me the safest next command.

Do not tell me to delete, reset, or force-push anything unless it is actually necessary.

---

# 45. NEVER RANDOMLY USE DANGEROUS GIT COMMANDS

Do not randomly run:

```bash
git reset --hard
```

or:

```bash
git push --force
```

These can destroy or overwrite work.

Ask Person 1 / ChatGPT first.

---

# 46. DEVELOPMENT DEPENDENCY

The complete METRA workflow should eventually be:

```text
PERSON 3
Create Instrument
        ↓
PERSON 3
Create Test Job
        ↓
PERSON 2
Load Regulatory Profile
        ↓
PERSON 2
Generate Applicable Test Plan
        ↓
PERSON 4
Execute Test
        ↓
PERSON 4
Calculate Result
        ↓
PASS / FAIL
        ↓
PERSON 5
Add Evidence
        ↓
PERSON 5
Submit for Review
        ↓
PERSON 5
Review / Approval
        ↓
PERSON 6
Generate Report
        ↓
PERSON 1
Integration + Audit + Deployment
```

---

# 47. SHARED FILES

Some files affect the entire project.

Examples:

```text
package.json
vite.config.*
tsconfig.*
main.tsx
App.tsx
global styles
shared types
API root
database configuration
authentication
global routing
```

These are normally controlled by Person 1.

If you need to change a shared file:

**Ask Person 1 first.**

---

# 48. MODULE OWNERSHIP

```text
PERSON 1
Core + Integration

PERSON 2
Regulatory

PERSON 3
Instruments + Jobs

PERSON 4
Tests + Calculations

PERSON 5
Workflow + Evidence

PERSON 6
Reports + Dashboard
```

You may inspect other modules.

You should not rewrite them without coordination.

---

# 49. IF YOUR MODULE NEEDS ANOTHER PERSON'S MODULE

Example:

Person 4 needs an MPE value.

Do NOT create your own duplicate MPE table.

Instead:

```text
Person 4
   ↓
Needs regulatory data
   ↓
Person 2's regulatory interface
   ↓
Use existing interface
```

Ask ChatGPT how to connect to the existing interface if necessary.

---

# 50. REGULATORY DATA RULE

Never invent regulatory values.

Do not randomly change:

```text
MPE
Accuracy Classes
Fees
Legal Limits
Verification Requirements
GATC Applicability
Certificate Requirements
```

If unsure:

```text
STOP
 ↓
Ask ChatGPT
 ↓
Verify the source
 ↓
Implement
```

Regulatory information should be versioned/configurable wherever practical.

---

# 51. COMPLETE TEAM WORKFLOW

Every person should follow this:

```text
┌───────────────────────────────┐
│ 1. Clone GitHub repository    │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 2. Find project folder path   │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 3. Open Antigravity           │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 4. Open Team ChatGPT link     │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 5. Tell ChatGPT Person #      │
│    + project location         │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 6. Get ONE Antigravity prompt │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 7. Paste into Antigravity     │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 8. Allow required actions     │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 9. Copy Antigravity output    │
└──────────────┬────────────────┘
               ↓
┌───────────────────────────────┐
│ 10. Paste output into ChatGPT │
└──────────────┬────────────────┘
               ↓
         More work?
          /      \
        YES       NO
         ↓         ↓
      Repeat    Inspect
                   ↓
                 Test
                   ↓
              git status
                   ↓
                Commit
                   ↓
                 Push
```

---

# 52. ANTIGRAVITY LIMIT / MODEL SWITCH FLOW

```text
Antigravity working
       ↓
Limit reached?
       │
      YES
       ↓
Switch to another authorized account
       ↓
Same local project
       ↓
Tell ChatGPT account changed
       ↓
Get inspection prompt
       ↓
Antigravity inspects current work
       ↓
Paste inspection result into ChatGPT
       ↓
Continue
```

If the current model's credits run out:

```text
Current model
     ↓
Limit reached
     ↓
Select available model
     ↓
Inspect current state
     ↓
Continue
```

---

# 53. CHATGPT LIMIT FLOW

```text
ChatGPT conversation getting too long
              ↓
Create continuation summary
              ↓
New ChatGPT conversation
              ↓
Paste summary
              ↓
Give project location
              ↓
Give Person Number
              ↓
Continue from existing code
```

---

# 54. IF YOU ARE STUCK

Never randomly modify code.

Send ChatGPT:

I am PERSON X working on METRA SIH26035.

I am stuck.

Project location:

C:\Users\YourName\Desktop\MetrIQ

Current branch:

[BRANCH]

What I was trying to do:

[EXPLAIN]

Antigravity's latest output:

[PASTE]

Error message, if any:

[PASTE]

Tell me the safest next step.

Give me only ONE next action.

If it requires coding, give me ONE Antigravity prompt.

If it requires a terminal command, give me the exact command.

---

# 55. FINAL END-TO-END TEST

After everyone's work has been integrated, Person 1 should test:

```text
Create Instrument
        ↓
Create Job
        ↓
Regulatory Requirements
        ↓
Test Plan
        ↓
Execute Tests
        ↓
Enter Observations
        ↓
Calculate Results
        ↓
PASS / FAIL
        ↓
Evidence
        ↓
Review
        ↓
Approval
        ↓
Generate Report
        ↓
Archive
```

---

# 56. THE 7 RULES EVERYONE MUST REMEMBER

```text
1. CLONE the repository.

2. FIND your exact project folder location.

3. DO NOT manually open the project folder in Antigravity.
   Give the location inside the Antigravity prompt.

4. IDENTIFY yourself to ChatGPT as Person 1–6.

5. ASK ChatGPT for ONE prompt at a time.

6. PASTE Antigravity's output back into ChatGPT.

7. INSPECT → COMMIT → PUSH your own branch.
```

---

# 57. THE MOST IMPORTANT CONCEPT

## Your project folder is the source of truth.

Not:

```text
Antigravity account
```

Not:

```text
ChatGPT conversation
```

Not:

```text
Antigravity model
```

The actual source of truth is:

```text
YOUR LOCAL METRA PROJECT FOLDER
```

Therefore:

```text
Change account → Continue
Change model → Continue
New ChatGPT chat → Continue
Chat limit → Continue
Antigravity limit → Continue
Computer restart → Continue
```

Always inspect the current project before continuing.

---

# 58. FINAL TEAM RESPONSIBILITY TABLE

| Person   | Workload | Main Responsibility | Main Output                        |
| -------- | -------: | ------------------- | ---------------------------------- |
| Person 1 |      10% | Core + Integration  | Working complete system            |
| Person 2 |      20% | Regulatory Engine   | Rules + applicability + test plans |
| Person 3 |      20% | Instruments + Jobs  | Instrument/job management          |
| Person 4 |      20% | Test Engine         | Tests + calculations + PASS/FAIL   |
| Person 5 |      20% | Workflow + Evidence | Evidence + review + audit          |
| Person 6 |      10% | Reports + Dashboard | Reports + dashboard + archive      |

---

# 59. FINAL SYSTEM

```text
                         METRA
                           │
                           ▼
                    INSTRUMENT
                           │
                           ▼
                       TEST JOB
                           │
                           ▼
                 REGULATORY ENGINE
                           │
                           ▼
                      TEST PLAN
                           │
                           ▼
                    TEST ENGINE
                           │
                           ▼
                    CALCULATIONS
                           │
                           ▼
                      PASS / FAIL
                           │
                           ▼
                      EVIDENCE
                           │
                           ▼
                       REVIEW
                           │
                           ▼
                       APPROVAL
                           │
                           ▼
                        REPORT
                           │
                           ▼
                       ARCHIVE
```



**Build your assigned module. Inspect it. Push it. Let Person 1 integrate it.**
