## Contributing to this Project

We welcome contributions to this project! To ensure a smooth and efficient collaboration, please follow these guidelines.

### How to Contribute

1.  **Fork the repository:** Start by forking the project to your GitHub account.
2.  **Clone your fork:** Clone your forked repository to your local machine.
    ```bash
    git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
    cd YOUR_REPO_NAME
    ```
3.  **Create a new branch:** Create a new branch for your feature or bug fix.
    ```bash
    git checkout -b feature/your-feature-name
    ```
4.  **Make your changes:** Implement your changes, ensuring they adhere to the coding standards and best practices outlined below.
5.  **Run tests:** Before submitting your changes, make sure all existing tests pass and add new tests for your changes.
    ```bash
    make test
    make smoke
    ```
6.  **Commit your changes:** Write clear and concise commit messages.
    ```bash
    git commit -m "feat: Add new feature X"
    ```
7.  **Push to your fork:** Push your changes to your forked repository.
    ```bash
    git push origin feature/your-feature-name
    ```
8.  **Create a Pull Request (PR):** Open a pull request from your fork to the `main` branch of the upstream repository. Provide a detailed description of your changes and reference any relevant issues.

### Coding Standards

*   **Style:** Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code. Use linters like `ruff` or `flake8`.
*   **Type Hints:** Use type hints for all function arguments and return values.
*   **Docstrings:** Write clear and concise docstrings for all public functions, classes, and modules.
*   **Comments:** Use comments sparingly to explain complex logic.

### Test Expectations

*   **Unit Tests:** All new features and bug fixes should be accompanied by unit tests.
*   **Integration Tests:** For significant changes, consider adding integration tests.
*   **Smoke Tests:** Ensure your changes do not break the existing smoke tests (`make smoke`).

### Code of Conduct

We adhere to a [Code of Conduct](CODE_OF_CONDUCT.md). Please review it before contributing.
