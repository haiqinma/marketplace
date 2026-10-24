# 共享测试库

`tester` 是社区共享的 Playwright/Chromium E2E 测试仓库。YeYing 社区所有项目仓库的 E2E 和用户流程用例统一在这里编写、维护和执行，不随被测项目的语言或框架变化。产品内部单元测试可以留在产品自己的原生测试套件中。

## 路径解析

1. 确定当前产品仓库根目录（优先使用 `git rev-parse --show-toplevel`）。
2. 读取本次 Project 客户端使用的 TOML 配置：显式 `--config`、`YEYING_PROJECT_CONFIG`、默认 `~/.yeying/skills/project/config.toml`，按此优先级选择。
3. 如果配置包含 `[tester].path`，绝对路径直接使用；相对路径以当前产品仓库根目录为基准。
4. 未设置时，使用 `<产品仓库父目录>/tester`。例如 `/workspace/opensource/project` 默认对应 `/workspace/opensource/tester`。

配置示例：

```toml
[project]
url = "https://project.example.com"
access_key = "yyak_..."
secret_key = "<secret>"

[tester]
path = "../tester"
```

`[tester]` 仅供 Agent 解析测试库位置；Project API 客户端继续只读取 `[project]`。不要输出或复制同一文件中的 AK/SK。

## 放置与执行

- E2E spec、用户旅程断言、对应 fixture 和 tester 专用 runner 配置必须放在 `tester`，不得在产品仓库中新建。
- `docs/test-cases/<product>.md` 是 tester 的 E2E 用例清单；实现或扩展用例时同步维护用例状态、spec 路径和覆盖统计。自动化 spec 放在 `products/<product>/tests/*.spec.ts`。
- 产品内部单元/组件测试可以留在产品仓库的原生测试套件，尤其是验证模块私有逻辑或产品 CI 强制要求的测试；不要复制 tester 已覆盖的用户流程断言。
- 实施前检查 `tester/README.md`、`CLAUDE.md`、对应产品用例清单、`products/<product>/playwright.config.ts` 和现有 spec，沿用其 fixtures、选择器、环境和数据清理约定，不另起一套。
- 使用 `pnpm test:<product>` 或该产品配置规定的命令执行；先核对 `TEST_ENV` 和目标服务。未经用户明确授权，不运行 `TEST_ENV=prod` 或其他可能触及生产数据的测试。
- 任务方案与 Project 记录应覆盖两个仓库的改动边界；交付时分别记录产品实现和 `tester` 用例的仓库、分支、commit、PR 与验证结果。

如果配置路径和默认位置都不存在，或无法访问 `tester`，先报告路径/权限阻塞并请求补齐配置或工作区。不要因此退回到产品仓库创建 E2E 用例；可以继续与测试无关且已获批的实现，但不能声称测试已完成。
