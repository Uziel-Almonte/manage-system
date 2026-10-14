# SonarCloud (optional)

The application CI workflow does not call SonarCloud. This repository includes a manual workflow and a scanner properties file so the project can be connected when an organization token exists.

## Connect

1. Create a project on SonarCloud for `Uziel-Almonte/manage-system`.
2. Set `sonar.projectKey` and `sonar.organization` in `sonar-project.properties` to the values SonarCloud shows.
3. Add the repository secret `SONAR_TOKEN`.
4. Run the **SonarCloud** workflow manually from the Actions tab (`.github/workflows/sonarcloud.yml`). It does not run on push or on pull requests.

Coverage is read from `coverage.xml`, which the Coverage job already uploads as an artifact. For a local scan, generate that file first:

```bash
pytest tests/ -m "not e2e" --cov=app --cov-report=xml --cov-report=term-missing
```
