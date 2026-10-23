GLITCHLOG — Multilingual Team Website
=====================================

This version applies practical patterns demonstrated in the two supplied HTML/CSS
tutorial videos: semantic page sections, a separate stylesheet, reusable CSS
variables, flex/grid layouts, consistent heading hierarchy, card-based content,
button/link states, hover transitions, and responsive layouts.

The GLITCHLOG identity remains based on the supplied logo: black, white, and
neon-lime. Motion respects prefers-reduced-motion.

Files (all in one folder; no nested project folders):
- app.py             Python standard-library backend
- index.html         Main UI, all pages, auth UI and language switch
- styles.css         Typography, layout, responsive rules, animations
- glitchlog-logo.jpg Supplied GLITCHLOG logo

Languages: Persian (FA), English (EN), Spanish (ES).

Run:
1. Install Python 3.10+ (no pip packages required).
2. Keep all four files in the same folder.
3. Run: python app.py
4. Open: http://127.0.0.1:8000

Accounts:
- User registration/login and profile editing are included.
- Admin credentials can be configured with GLITCHLOG_ADMIN_USER and
  GLITCHLOG_ADMIN_PASSWORD environment variables.
- Change default admin credentials before any internet deployment.

This is a local development starter. Before public deployment, configure HTTPS,
persistent secure sessions, rate limiting, CSRF protection, secure upload
handling and production-grade server settings. Do not expose the development
server directly to the public internet.


Updates: Telegram contact link and anonymous message form. Anonymous messages are saved in applications.db and visible only in the administrator panel. No sender name, email, phone, or IP address is collected by this feature. The site supports Persian, English, and Spanish for the contact flow and expanded UI translations.
