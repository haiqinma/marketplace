# Collection Plan

This repository should become the public marketplace source for chat.

The product scope covers skills, tool packages, model providers, and storage capabilities.

## Sources

Collect from:

- official examples from this organization
- community pull requests
- high-quality open source prompt libraries with compatible licenses
- task workflows from Tool Server examples
- product, research, writing, coding, design, and operations templates

Do not bulk-import low-quality prompt dumps. Every skill should be rewritten into the current skill package spec.

## Categories

Start with:

- research
- reading
- writing
- coding
- product
- design
- image
- operations
- finance
- community

## Quality Bar

A skill should answer:

- What task does it solve?
- What inputs does it expect?
- What output should it produce?
- Which model capability does it need?
- Which built-in tools or Tool Server services does it use?
- Can the user run it immediately after install?

## Chat Discovery Integration

Chat should load this repository as a remote skill source:

```txt
https://raw.githubusercontent.com/yeying-community/marketplace/main/packages.json
```

Discovery should show:

- installed local skills
- built-in skills
- remote marketplace skills

Remote marketplace skill actions:

- `Install`: write package into local skill store
- `Manage`: open installed skill
- `Configure`: open missing tool/model dependency

## Release Process

1. Author submits a PR with a new file under `skills/chat/<skill-id>/<lang>.json`.
2. CI runs `npm run check`.
3. Maintainer reviews quality, safety, and license.
4. Merge updates `packages.json`.
5. Chat discovers the new skill from the raw GitHub URL.
