# ClAuSy — Session Log & Roadmap

---

## מה שנבנה

### אפליקציה
- `main.py` — נקודת כניסה, פותח חלון CustomTkinter (זוכר גודל/מקסום אחרון)
- `app.py` — ממשק גרפי מלא: Settings / Directories / CLAUDE.md Map / Agents & Routines / Explained
  - ממשק הועבר ל-CustomTkinter (במקום Tkinter רגיל) — פלטת צבעים כהה (BG, SURF, SURF2, SURF3, WARN)
  - ToggleCircle — עיגול לחיץ לכל מקור הרשאה
  - ScrollableFrame — רשימה גלילה
  - DirectoryRow — שורת תיקייה עם checkbox, label, path, 3 toggles
    - סימון ⚠ אם התיקייה כבר לא קיימת בדיסק (ויש לה הרשאה פעילה)
    - סימון ⚠ אם התיקייה חופפת לתיקייה אחרת ברשימה (אחת הורה של השנייה)
    - תפריט קליק ימני: Open / Copy path / Remove
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
- `claude_meta.py` — סריקה טהורה (ללא side-effects) של CLAUDE.md / subagents / hooks
  - `find_claude_md_files()`, `find_agents()`, `find_hooks()`
  - `check_rtl_first_line()`, `claude_md_stats()`, `find_agent_description_issues()`
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
- `storage.py` — שמירת העדפות UI ב-`~/.clauSy/settings.json` (כולל גודל/מצב חלון, מצב legend)

### בדיקות
- `test_config_manager.py` + `test_claude_meta.py` — 102 unit tests, כולם עוברים (`python -m pytest`)

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
- `ClAuSy_Feature_Ideas.xlsx` — 130 רעיונות מסודרים לפי קטגוריה/עדיפות, עם עמודות "Do it?"/"Status" למעקב
  - #1-100: רעיונות מקוריים
  - #101-130: 30 רעיונות מבוססי מחקר ברשת (GitHub issues אמיתיים של anthropics/claude-code, תקרית YOLO-mode מתועדת, docs רשמיים)
- 20 רעיונות שסומנו Done: #5, #6, #8, #10, #14, #18, #19, #51, #53, #99, #101, #102, #103, #106, #109, #111, #113, #119, #122, #130
- `CHANGELOG.md` — מתעד את כל הפיצ'רים לפי גרסה (Keep a Changelog format)

---

## קבצי עזר קשורים

| קובץ | מיקום | תוכן |
|------|--------|-------|
| `github_fixed.md` | `C:\meir\Claude\NewProjectElements\` | Checklist לשיפור כל ריפו בGitHub |
| `open-source-promotion-guide.md` | `C:\meir\MyObsidianClaudedFiles\AppPublish\` | מדריך פרסום מפורט לכל פלטפורמה |
| `CLAUDE.md` (גלובלי) | `C:\Users\ginot\.claude\` | הוראות קלוד-קוד גלובליות (ללא attribution) |
