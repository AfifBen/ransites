# Contributing to RANSites

Thanks for contributing to RANSites.

## Workflow

1. Create a feature branch from `main`
2. Implement and test your changes locally
3. Open a Pull Request with a clear description
4. Request review before merge

## Branch Naming

- `feature/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`

Examples:

- `feature/site-lifecycle-v2`
- `fix/import-cell-validation`

## Commit Message Style

Use short and explicit messages:

- `feat: add site profile nearest-sites map`
- `fix: validate azimuth range on sector create`
- `docs: update README quick start`

## Code Guidelines

- Keep changes focused and small
- Preserve existing project structure and naming
- Add comments only where logic is non-obvious
- Avoid introducing breaking behavior without migration path

## Database & Migrations

When models change:

1. Create migration
2. Review generated script
3. Apply migration locally and test affected flows

## Testing Checklist

Before opening a PR, verify:

- Login/logout
- Table listing pages
- Add/Edit/Delete critical entities
- Import templates + import flows
- Allplan/KML exports

## Security Notes

- Never commit `.env`, secrets, or local DB files
- Use least-privilege credentials for integrations
- Keep access controls aligned with role scope rules

