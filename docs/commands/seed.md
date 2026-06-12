---
seo:
  title: seed - DBWarden Documentation
  description: Manage seed data for a database.
  canonical: https://emiliano-gandini-outeda.github.io/DBWarden/commands/seed/
  robots: index,follow
  og:
    type: website
    title: seed - DBWarden Documentation
    description: Manage seed data for a database.
    url: https://emiliano-gandini-outeda.github.io/DBWarden/commands/seed/
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
    site_name: DBWarden Documentation
  twitter:
    card: summary_large_image
    title: seed - DBWarden Documentation
    description: Manage seed data for a database.
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
  schema_jsonld:
    '@context': https://schema.org
    '@type': WebPage
    name: seed - DBWarden Documentation
    url: https://emiliano-gandini-outeda.github.io/DBWarden/commands/seed/
    description: Manage seed data for a database.
    image: https://emiliano-gandini-outeda.github.io/DBWarden/assets/icon.png
    publisher:
      '@type': Organization
      name: Emiliano Gandini Outeda
---

# `seed`

Manage seed data for a database.

## Subcommands

- `seed create`: create a new file seed (legacy)
- `seed apply`: apply pending seeds (file + code seeds)
- `seed list`: list seeds and their status
- `seed rollback`: roll back applied seeds

---

## `seed create`

Create a new file-based seed file (SQL or Python). For new projects, prefer [code seeds](../seeds.md#code-seeds-recommended) instead.

### Usage

```bash
dbwarden seed create "seed initial data" --database primary
dbwarden seed create "populate lookup tables" --database primary --type python
```

### Options

- `--database`, `-d`: target database handle
- `--type`: `sql` (default) or `python`
- `--verbose`, `-v`

---

## `seed apply`

Apply pending seeds. Both file seeds and [code seeds](../seeds.md#code-seeds-recommended) are discovered and applied.

### Usage

```bash
dbwarden seed apply --database primary
dbwarden seed apply --database primary --version 0003
dbwarden seed apply --database primary --dry-run
dbwarden seed apply --all
```

### Options

- `--database`, `-d`
- `--all`, `-a`: apply across all configured databases
- `--version`: apply up to this seed version
- `--dry-run`: preview without executing
- `--verbose`, `-v`

---

## `seed list`

List seeds and their applied status. Includes both file seeds and code seeds.

### Usage

```bash
dbwarden seed list --database primary
dbwarden seed list --all
dbwarden seed list --prune              # clean up orphaned tracking records
```

### Options

- `--database`, `-d`
- `--all`, `-a`
- `--prune`: remove tracking records for seed files that no longer exist on disk
- `--verbose`, `-v`

---

## `seed rollback`

Roll back applied seeds. Removes the tracking record, allowing the seed to be re-applied. Does **not** reverse data changes.

### Usage

```bash
dbwarden seed rollback --database primary
dbwarden seed rollback --database primary --count 2
dbwarden seed rollback --database primary --to-version 0003
```

### Options

- `--database`, `-d`
- `--all`, `-a`: rollback on all databases
- `--count`, `-c`: number of seeds to roll back (default: 1)
- `--to-version`, `-t`: roll back to this seed version
- `--verbose`, `-v`

See also: [Seed Management](../seeds.md)
