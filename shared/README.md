# Shared — Reusable Components
### Roles, modules, and plugins used across multiple chapters

*The Ansible AIOps Playbook: Building Self-Healing Linux Systems at Scale*
https://github.com/balaramaa/ansible-aiops-playbook

---

## Contents

```
shared/
├── roles/                       # Reusable Ansible roles (used in 2+ chapters)
├── modules/                     # Custom Ansible modules
├── inventory-plugins/           # Custom dynamic inventory plugins
└── filters/                     # Custom Jinja2 filter plugins
```

Components here are imported by chapter playbooks using relative paths or
the `roles_path` setting in `ansible.cfg`.
