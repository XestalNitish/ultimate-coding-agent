GOAL: Autonomous SWE-Agent Style Bug Resolver & PR Reviewer System using LangGraph/CrewAI, Python, Git API, and Docker/E2B

REQUIREMENTS:
1. Triage Agent must analyze GitHub issues and perform code search/embeddings to identify relevant files within the codebase.
2. Developer Agent must modify code and execute bug fixes autonomously based on triaged issue analysis.
3. Testing Agent must execute tests in a sandbox/Docker container to verify that the bug fix introduces no additional regressions.
4. PR Agent must automatically create a Pull Request with a detailed explanation only after all automated tests pass successfully.
5. The entire workflow must be orchestrated using LangGraph or CrewAI frameworks in Python.
6. All interactions with the codebase and repository state must be managed via the Git API.

ACCEPTANCE CHECKS:
1. Triage Agent successfully identifies and extracts relevant files for the given GitHub issue.
2. Developer Agent successfully modifies code and resolves the specific bug without breaking core functionality.
3. Testing Agent successfully runs tests in the Docker/E2B sandbox and confirms zero test failures.
4. PR Agent successfully creates an automated Pull Request containing a detailed explanation of the fix.
5. The complete agent workflow executes seamlessly without manual intervention.

CONSTRAINTS:
1. Tech stack strictly limited to LangGraph or CrewAI for agent orchestration.
2. Core implementation language must be Python.
3. Git API must be utilized for all codebase and repository state management.
4. Testing must be executed within Docker or E2B sandbox environments.
5. Forbidden: Any manual intervention or manual PR creation by the user.