# Repository instructions

- App packages live under `apps/<key>/<version>/`; app-specific operational notes live under `docs/apps/`.
- Follow official application install docs as well as 1Panel package conventions. Record source URLs and package revision in `specs/<key>/<version>.json`.
- Use official, versioned images. Verify container runtime users before changing permissions; do not guess UIDs or add unnecessary hooks.
- Use `${CONTAINER_NAME}`, `PANEL_APP_PORT_*`, relative persistence mounts, the external `1panel-network`, and `createdBy: Apps` for all services.
- Keep root descriptions and form labels in the ten supported locales. English fallback for app-specific text is acceptable when explicitly documented.
- Only credential-free default `.env` files belong in app packages. Never run a package directly inside `apps/` or commit runtime databases.
- Updating app resources is separate from upgrading installed instances. Document data migrations; never migrate production data as part of repository synchronization.
- Run `python scripts/validate.py --compose`, `python -m unittest discover -s tests -v`, and the relevant Docker smoke test after executable changes.
- For documentation-only changes, check links and commands without rerunning unrelated containers.
- Keep changes local unless publishing, deploying, pushing, or creating a GitHub release has been requested.
