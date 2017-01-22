Qubes Manager
==============

Managing translations
----------------------

### Adding new language

1. Add `i18n/qubesmanager_LANGUAGECODE.ts` (replace `LANGUAGECODE` with actual code,
   for example `es`) to `qubesmanager.pro` - `TRANSLATIONS` setting.
2. Run `make res update_ts`

### Regenerating translation source files (`.ts`)

    make res update_ts

This will keep translated strings, but will add new ones.

### Updating translations

Commit updated `.ts` files into `i18n` directory.
