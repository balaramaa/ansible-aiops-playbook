# Contributing to The Ansible AIOps Playbook Repository

## Reporting Errors (Errata)

If you find an error in the book's code examples:

1. Open an Issue: https://github.com/balaramaa/ansible-aiops-playbook/issues/new
2. Use the title format: [Ch N] Brief description of the error
3. Include: chapter/section, incorrect code, correct version, OS and Ansible version

## Submitting Pull Requests

1. Fork the repository
2. Create a branch: git checkout -b fix/ch05-compliance-task
3. Make your changes and test in the lab environment
4. Submit a Pull Request with a clear description

## Code Standards

All Ansible code must pass ansible-lint, use fully qualified module names
(ansible.builtin.*), have a name on every task, and support --check mode.

## Contact

Author: Balaramakrishna Alti
Email: balaramaa@gmail.com
LinkedIn: https://www.linkedin.com/in/balaramakrishna-alti-b9924b278
