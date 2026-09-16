# ClAuSy — Session Log & Roadmap

---

## מה שנבנה

### אפליקציה
- `main.py` — נקודת כניסה, פותח חלון CustomTkinter (זוכר גודל/מקסום אחרון)
- `app.py` — ממשק גרפי מלא: Settings / Directories / CLAUDE.md Map / Agents & Routines / Git Push / Explained
  - ממשק הועבר ל-CustomTkinter (במקום Tkinter רגיל) — פלטת צבעים כהה (BG, SURF, SURF2, SURF3, WARN)
  - ToggleCircle — עיגול לחיץ לכל מקור הרשאה
  - ScrollableFrame — רשימה גלילה
  - DirectoryRow — שורת תיקייה עם checkbox, label, path, 3 toggles
    - סימון ⚠ אם התיקייה כבר לא קיימת בדיסק (ויש לה הרשאה פעילה)
    - סימון ⚠ אם התיקייה חופפת לתיקייה אחרת ברשימה (אחת הורה של השנייה)
    - תפריט קליק ימני: Open / Copy path / Show effective permissions / Remove
  - List view + Thumbnail view
  - תיבת חיפוש חופשית (מסננת לפי label או path, גם ב-list וגם ב-thumbnail)
  - Legend מתקפל/נפתח (עם שמירת מצב)
  - מיון: שם A→Z / Z→A / תאריך ↑↓
  - Multi-select + column-header toggle
  - Undo stack — 30 רמות
  - קיצורי מקלדת: Ctrl+Z (undo), Delete (מחיקת שורות מסומנות), Ctrl+F (פוקוס לחיפוש)
  - Execute עם progress bar (background thread)
  - ולידציה ויזואלית ✔/✗/— ליד כל שדה path בSettings
  - כפתור "✔ Check" לבדיקת קבצי config
  - כפתור "🔒 Deny Secrets" — מוסיף deny rules ל-.env/*.pem/*.key/id_rsa/credentials.json וכו'
  - כפתור "🐞 Report Confusing Config" — פותח GitHub issue עם title/body ממולאים מראש
  - כפתור "↩ Restore" ליד כל שדה path — משחזר מה-backup האחרון
  - באנר אזהרה אם permissions.defaultMode = bypassPermissions ("YOLO mode")
  - רשימת כל קבצי claude_desktop_config.json שנמצאו במחשב (Windows Store vs. classic) עם אפשרות לבחור
  - דיאלוג "מה השתנה" (added/removed/permission flips) לפני כתיבה ב-Execute
  - אזהרה אם קובץ config השתנה בדיסק חיצונית מאז הטעינה האחרונה (לפני Execute)
  - CLAUDE.md Map tab — איפה כל קובצי ההוראות/config נמצאים, כולל:
    - סימון ⚠ RTL אם יש עברית בקובץ אבל לא בשורה הראשונה (Obsidian לא יזהה RTL אוטומטית)
    - ספירת מילים/שורות + אזהרת "ארוך מדי" (מבוסס על ~150 שורות, לא מילים — תואם את התנהגות Claude בפועל)
  - Agents & Routines tab — subagents ו-hooks מכל הפרויקטים העוקבים
    - סימון ⚠ ל-subagent עם description חסר/קצר מדי/זהה לאחר
  - Git Push tab — סורק כל תיקייה עוקבת (ותת-תיקיות ישירות שלה) לריפוזיטוריז גיט
    - סטטוס לכל ריפו: branch, badge אדום "⬆ N unpushed" / ירוק "✔ pushed" / "no upstream", badge כתום למספר שינויים לא שמורים (uncommitted)
    - badge "⚠ direct on main" אם יש קומיטים לא-דחופים ישירות על main/master
    - badge "⇕ N behind" + אזהרה בדיאלוג ה-push אם הריפו התפצל מה-remote (push רגיל צפוי להידחות; ClAuSy לעולם לא עושה force-push)
    - badge "🌿 new branch" אם ה-branch הנוכחי לא נראה בסריקה קודמת (נשמר ב-storage.py)
    - badge "⚠ history rewritten" + אזהרה בדיאלוג ה-push אם ה-HEAD הקודם שנשמר כבר לא ancestor של ה-HEAD הנוכחי (amend/rebase)
    - תצוגת הקומיטים הלא-דחופים האחרונים (hash + הודעה), tooltip לרשימה המלאה
    - checkbox לכל ריפו + "☑ Select Unpushed" / "☐ Select None" + כפתור "⬆ Push Selected" (עם דיאלוג אישור לפני push בפועל, כי זו פעולה שמשפיעה על remote)
    - כפתור "Push" בודד לכל שורה, וכפתור "Open" לפתיחת התיקייה
    - הריצה (סריקה + push) על thread נפרד כדי לא לתקוע את הממשק, עם progress bar וסטטוס לכל שורה
  - באנר "כמה זמן YOLO mode פעיל" (ימים, לא רק "פעיל עכשיו") — נשמר ב-storage.py
  - באנר אזהרה על מפתחות לא-מזוהים ב-settings.json (typo / setting שהוסר)
  - כפתור "🔍 Find Ignored Secrets" — סורק קבצי סוד (.env/*.pem/*.key/credentials.json) שמוסתרים ב-.gitignore אבל עדיין קריאים ל-Claude
  - Permission rule simulator בSettings — מקלידים command/path ורואים איזה allow/deny rule תואם ומה הverdict
  - סימון ⚠ בDirectories אם התיקייה נראית כמו נתיב מערכת/credentials רגיש (System32, /etc, ~/.ssh, ~/.aws...)
  - באנר אזהרה על Bash allow rules עם bare wildcard `*` (במקום `:*` הבטוח) — יכול להתאים לתווי shell כמו `; && |`
  - דיאלוג "השתנה חיצונית" משודרג — מזהיר במפורש אם rules (לא תיקיות) נעלמו מ-settings.json
  - באנר אזהרה אם settings.local.json נמצא tracked בgit במקום gitignored (בדיקה ישירה מול `git ls-files`)
  - "Show effective permissions" בתפריט קליק ימני — ממזג global settings.json + project-level .claude/settings.json + Claude Desktop לverdict אחד (ALLOW/DENY/ASK)
- `claude_meta.py` — סריקה טהורה (ללא side-effects) של CLAUDE.md / subagents / hooks
  - `find_claude_md_files()`, `find_agents()`, `find_hooks()` (כולל `commands` בפועל לכל hook)
  - `check_rtl_first_line()`, `claude_md_stats()`, `find_agent_description_issues()`
  - `find_dangerous_hook_commands()` — תבניות זדוניות/הרסניות ידועות (curl|sh, base64 -d, PowerShell מקודד, rm -rf, git push --force)
  - `find_hook_loop_risks()` — hooks על Stop/SubagentStop/UserPromptSubmit שקוראים ל-`claude` שוב
- `git_status.py` — סריקת ריפוזיטוריז גיט וסטטוס push (ללא side-effects חוץ מ-`push_repo()`)
  - `find_git_repos()`, `get_repo_status()` (כולל `direct_on_main`, `behind`, `head_sha`), `scan()`, `push_repo()`
  - `is_ancestor()` — לזיהוי amend/rebase מול ה-HEAD הידוע האחרון
  - `is_path_tracked()`, `find_tracked_settings_local()` — settings.local.json שנכנס לgit בטעות
- `config_manager.py` — קריאה/כתיבה בטוחה לקבצי Claude
  - `ConfigError` — exception ל-JSON פגום
  - `validate_path()` — בדיקת קובץ לפני שימוש
  - `read_all_dirs()` — מאחד נתונים מכל המקורות
  - `apply_changes()` — כותב בלי לשבור תוכן סביב
  - `find_overlapping_paths()` — מזהה תיקיות חופפות (הורה/ילד) ברשימה
  - `find_allow_deny_conflicts()`, `add_deny_patterns()`, `get_permission_mode()`
  - `list_backups()`, `restore_last_backup()` — rotation של עד 5 גיבויים לכל קובץ
  - `find_cd_config_candidates()` — כל מיקומי claude_desktop_config.json הקיימים בפועל
  - `file_fingerprint()` — לזיהוי שינוי חיצוני בקובץ לפני כתיבה
  - `summarize_changes()` — diff בין מצב טעון למצב לפני Execute
  - `find_unknown_keys()` — מפתחות top-level ב-settings.json שלא מוכרים ל-ClAuSy
  - `find_gitignored_secrets()` — קבצי סוד שמוסתרים ב-.gitignore
  - `get_permission_rules()`, `simulate_permission()` — סימולטור חוקי הרשאה (תומך בתחביר `:*` של Bash)
  - `is_sensitive_system_path()` — זיהוי נתיבי מערכת/credentials רגישים
  - `count_non_path_rules()`, `find_unsafe_bash_wildcards()` — bare `*` בBash allow rules
  - `get_effective_permissions()` — מיזוג global + project-level + Claude Desktop לverdict אחד
- `storage.py` — שמירת העדפות UI ב-`~/.clauSy/settings.json` (כולל גודל/מצב חלון, מצב legend, branches ידועים לכל ריפו, HEAD sha אחרון לכל ריפו, מתי הופעל YOLO mode)

### בדיקות
- `test_config_manager.py` + `test_claude_meta.py` + `test_git_status.py` + `test_storage.py` — 189 unit tests, כולם עוברים (`python -m pytest`)

### GitHub
- ריפו: https://github.com/MeirYaakovi/ClAuSy
- נושאים (topics): python, tkinter, claude, claude-ai, claude-code, claude-desktop, mcp, anthropic, developer-tools, open-source
- Release: v1.0.0 — https://github.com/MeirYaakovi/ClAuSy/releases/tag/v1.0.0
- רישיון: MIT
- README עם badges

---

## מה שנשאר לעשות

### ידני (לא ניתן דרך קוד)
- [ ] **Social Preview image** — GitHub → Settings → Social Preview → העלה תמונה 1280×640px
- [ ] **Pin הריפו** — GitHub profile → Customize → Pin ClAuSy
- [ ] **GIF / סרטון demo** — להוסיף לREADME ולפרסומים (30 שניות מספיקות)

### פרסום אורגני
ראה מדריך מפורט ב-`C:\meir\MyObsidianClaudedFiles\AppPublish\`
- [ ] Reddit — r/ClaudeAI, r/Python, r/SideProject
- [ ] Hacker News — Show HN
- [ ] Discord — Anthropic Official, AI Hacker House
- [ ] X (Twitter) — thread עם GIF
- [ ] Dev.to / Hashnode — פוסט על הבעיה שנפתרה
- [ ] Awesome Lists — PR ל-`awesome-claude` ו-`awesome-mcp` בGitHub

### שיפורים אפשריים לאפליקציה
- [ ] GitHub Actions CI — `.github/workflows/test.yml` להרצת טסטים על כל push
- [ ] CONTRIBUTING.md — הנחיות לתורמים
- [ ] Issue templates — תבנית לדיווח באגים
- [ ] Thumbnail view — הוספת toggles אינטראקטיביים (כרגע קליק עובד רק בlist)

### רשימת רעיונות לפיצ'רים
- `ClAuSy_Feature_Ideas.xlsx` — 160 רעיונות מסודרים לפי קטגוריה/עדיפות, עם עמודות "Do it?"/"Status"/"Date Added" למעקב
  - #1-100: רעיונות מקוריים
  - #101-130: 30 רעיונות מבוססי מחקר ברשת (GitHub issues אמיתיים, תקרית YOLO-mode מתועדת, docs רשמיים)
  - #131-160: 30 רעיונות סבב 3 (GitHub issues אמיתיים על permission precedence, wildcard matching, hook loops, ChainDrop npm worm, force-push incidents, plugin marketplaces)
- 42 רעיונות שסומנו Done: #5, #6, #8, #10, #14, #17, #18, #19, #30, #51, #53, #79, #99, #101, #102, #103, #104, #105, #106, #107, #109, #111, #113, #116, #119, #122, #123, #130, #131, #132, #134, #135, #137, #143, #144, #147, #148, #149, #153, #157, #159, #160
  - #17, #30, #104 התגלו כבר-implemented מסבבים קודמים ולא סומנו — תוקן בסבב 4
- `CHANGELOG.md` — מתעד את כל הפיצ'רים לפי גרסה (Keep a Changelog format)

---

## קבצי עזר קשורים

| קובץ | מיקום | תוכן |
|------|--------|-------|
| `github_fixed.md` | `C:\meir\Claude\NewProjectElements\` | Checklist לשיפור כל ריפו בGitHub |
| `open-source-promotion-guide.md` | `C:\meir\MyObsidianClaudedFiles\AppPublish\` | מדריך פרסום מפורט לכל פלטפורמה |
| `CLAUDE.md` (גלובלי) | `C:\Users\ginot\.claude\` | הוראות קלוד-קוד גלובליות (ללא attribution) |
