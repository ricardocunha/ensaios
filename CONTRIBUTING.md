# Working on an article

## 1. Start

```bash
git switch main && git pull
git switch -c article/<yyyy-mm>-<slug>          # e.g. article/2026-11-rag-evals
cp -R _template articles/<yyyy-mm>-<slug>
```

Use the month you plan to publish in. The slug should be short, lowercase and hyphenated.

## 2. Write and build

- Drafts go in `article-en.md` / `article-pt-br.md` / `linkedin-*.md`. Mark anything not yet measured as `[[RESULT: …]]` and anything not yet confirmed as `[[VERIFY: …]]`. Never invent a number to fill a gap.
- Code goes in `code/`, as its own project. Python: `cd code && uv init --lib`. Keep data, model weights and run outputs out of git (`code/.gitignore`).
- Commit as you go. The branch is the article's history.

## 3. Publish checklist

Run `scripts/check-article.sh articles/<yyyy-mm>-<slug>` and resolve everything it reports:

- [ ] No `[[RESULT]]` / `[[VERIFY]]` placeholders left in any draft.
- [ ] Every number in the drafts comes from a run you can point to (e.g. the code's `docs/RESULTS.md`).
- [ ] The code's tests pass and its README quickstart works from a clean checkout.
- [ ] No secrets (`.env` is never committed), no personal data, no real documents.
- [ ] Links point to `main` (`…/tree/main/articles/<yyyy-mm>-<slug>`), which is where the article will live after the merge.
- [ ] The article's row is added to the root README's table.

## 4. Merge

```bash
git switch main && git pull
git merge --no-ff article/<yyyy-mm>-<slug> -m "Publish: <title>"
git tag published/<yyyy-mm>-<slug>
git push && git push --tags
```

`--no-ff` keeps each article's work grouped under one merge commit, and the tag marks exactly what was published.

The repository stays **private until the first article is published**. After that first merge:

```bash
gh repo edit ricardocunha/ensaios --visibility public --accept-visibility-change-consequences
```

Before going public, check that no article branch holds anything you wouldn't publish. Branches become visible too.
