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

### Pushing translations to transifex
You'll need a token (for your own transifex acount, to configure it just run
tx config once).

tx push -s

### Getting translation from transifex
tx pull


Tests
----------------------

Located in the tests/ directory.

To run qube manager and backup tests:
    python3 test_name.py -v

To run global settings tests:
    sudo systemctl stop qubesd; sudo -E python3 test_global_settings.py -v ; sudo systemctl start qubesd
