# Deploying aspenintegra.com

The site is an [Astro](https://astro.build) static site. GitHub Actions builds it on
every push to `main` and uploads the result to your hosting over FTP/FTPS.

## 1. One-time GitHub setup

1. Create a **public** repository named `aspenintegra-site` under your `aspen8494`
   account: <https://github.com/new> (leave it empty — no README, no .gitignore).
2. Add the deploy secrets under **Settings → Secrets and variables → Actions →
   New repository secret**:

   | Secret | Value | Where to find it |
   |---|---|---|
   | `FTP_SERVER` | `ftp.aspenintegra.com` (or your host's FTP hostname/IP) | Hosting welcome email / cPanel → FTP Accounts |
   | `FTP_USERNAME` | your cPanel/FTP username | cPanel → FTP Accounts |
   | `FTP_PASSWORD` | your FTP password | create a dedicated FTP user in cPanel |
   | `FTP_SERVER_DIR` *(optional)* | e.g. `/home/USERNAME/public_html` | defaults to `./public_html/` |
   | `FTP_PROTOCOL` *(optional)* | `ftps` (default) or `ftp` | try `ftps` first; some hosts only do plain `ftp` |
   | `FTP_PORT` *(optional)* | `21` (default) | hosting docs |

3. Push the site (or use **Run workflow** on the Actions tab) — the first deploy
   uploads `dist/` to your document root.

## 2. Point the domain

In your domain registrar's DNS settings:

| Record | Host | Value | TTL |
|---|---|---|---|
| `A` | `@` | your hosting account's IP address | 3600 |
| `CNAME` | `www` | `aspenintegra.com` | 3600 |

If the domain was registered with the same company that provides the hosting, the
nameservers are usually already pointed correctly and this step is done.

## 3. Verify

- `https://aspenintegra.com` shows the homepage.
- `https://aspenintegra.com/research/` lists both flagship projects.
- Any URL like `https://aspenintegra.com/whatever/` shows the styled 404.

## Editing content

| What | How |
|---|---|
| Blog post | add `src/content/blog/my-post.md` (frontmatter: title, description, pubDate, tags) |
| Research project | add `src/content/research/my-project.md` (frontmatter: title, description, pubDate, tags, repo, weight, status) |
| Site name, email, links | `src/config.ts` |
| Colors, fonts, cards | `src/styles/global.css` (CSS variables at the top) |
| Navigation | `NAV` in `src/config.ts` |
| CV | `src/pages/cv.astro` |
| Favicon | `public/favicon.svg` · Social share image | `public/og.png` (1200×630) |

Commit and push to `main` — the site redeploys automatically (~2–3 min).

## Local development

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # static output in dist/
```
