# ClAuSy — Session Log & Roadmap

---

## מה שנבנה

### אפליקציה
- `main.py` — נקודת כניסה, פותח חלון Tkinter מקסימייזד
- `app.py` — ממשק גרפי מלא: Settings tab + Directories tab
  - פלטת צבעים כהה (BG, SURF, SURF2, SURF3)
  - ToggleCircle — עיגול לחיץ לכל מקור הרשאה
  - ScrollableFrame — רשימה גלילה
  - DirectoryRow — שורת תיקייה עם checkbox, label, path, 3 toggles
  - List view + Thumbnail view
  - מיון: שם A→Z / Z→A / תאריך ↑↓
  - Multi-select + column-header toggle
  - Undo stack — 30 רמות
  - Execute עם progress bar (background thread)
  - ולידציה ויזואלית ✔/✗/— ליד כל שדה path בSettings
  - כפתור "✔ Check" לבדיקת קבצי config
- `config_manager.py` — קריאה/כתיבה בטוחה לקבצי Claude
  - `ConfigError` — exception ל-JSON פגום
  - `validate_path()` — בדיקת קובץ לפני שימוש
  - `read_all_dirs()` — מאחד נתונים מכל המקורות
  - `apply_changes()` — כותב בלי לשבור תוכן סביב
- `storage.py` — שמירת העדפות UI ב-`~/.clauSy/settings.json`

### בדיקות
- `test_config_manager.py` — 26 unit tests, כולם עוברים
  - TestReadAllDirs (9 tests)
  - TestApplyChanges (11 tests)
  - TestValidatePath (6 tests)

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

---

## קבצי עזר קשורים

| קובץ | מיקום | תוכן |
|------|--------|-------|
| `github_fixed.md` | `C:\meir\Claude\NewProjectElements\` | Checklist לשיפור כל ריפו בGitHub |
| `open-source-promotion-guide.md` | `C:\meir\MyObsidianClaudedFiles\AppPublish\` | מדריך פרסום מפורט לכל פלטפורמה |
| `CLAUDE.md` (גלובלי) | `C:\Users\ginot\.claude\` | הוראות קלוד-קוד גלובליות (ללא attribution) |
