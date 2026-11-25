# 维护与发布

## 新增应用或版本

1. 从官方仓库或其链接的官方文档确认 Docker 安装方式、镜像、端口、挂载和运行用户。对每个必要的 host 操作记录官方依据。
2. 在 `apps/<key>/<version>/` 添加包，版本目录不加 `v`。应用根目录包含元数据、180×180 且不超过 10 KiB 的 PNG、中英文简介和上游许可信息。
3. 在 `specs/<key>/<version>.json` 记录 `key`、`version`、`package_revision`、`services`（name/image）、`source_evidence`；可以保留更完整的生成规格。记录镜像支持的架构、数据目录权限及已测试平台。
4. 在 `docs/apps/<key>.md` 记录安装参数、迁移、备份、官方来源和测试边界。更新根 README 应用列表。
5. 运行校验器、相关工具测试和容器测试；记录测试架构。新增应用也要增加自己的 smoke 测试并加入 CI。

所有容器加入外部 `1panel-network`，设置 `createdBy: Apps` 和 `restart: always`。主容器名使用 `${CONTAINER_NAME}`；次容器使用 `${CONTAINER_NAME}-<service>`。公开端口使用 `PANEL_APP_PORT_*` 字段，敏感字段使用 `password`，默认不包含真实秘密。

持久化目录使用相对路径并提交 `.gitkeep`。非 root 用户的写权限和 UID/GID 必须有官方证据。没有必要的初始化、迁移或清理动作时不添加生命周期脚本。

根描述和表单标签包含 `en`、`es-es`、`ja`、`ms`、`pt-br`、`ru`、`ko`、`zh-Hant`、`zh`、`tr`。通用标签复用现有翻译；专有文案缺少可靠翻译时允许英文回退，并注明。

`.gitignore` 只是辅助防护。版本目录内 `.env` 为包默认值而保留可跟踪状态，提交前仍须校验其内容。不要直接在 `apps/` 中运行容器。

## 检查

```bash
python scripts/validate.py --compose
python -m unittest discover -s tests -v
python scripts/smoke_bark.py --mysql
```

Docker 已运行时，可以用 `RUN_DOCKER_PERMISSION_TEST=1 python -m unittest discover -s tests -v` 增加 Linux 文件权限回归。该测试在 Docker 原生数据卷中创建 root 所有、`0600` 的模拟数据库，验证普通用户不可读、离线复制成功且权限保持不变；CI 默认执行此检查。

校验器会解析 YAML、拒绝重复键，检查主要格式、字段、默认凭据、镜像与规格一致性、持久化目录、脚本格式及语法。它不是完整的 1Panel schema 或安全审计，不能验证官方来源真实性或镜像架构，也不能替代实际安装和升级测试。

容器测试覆盖本机架构；发布时区分“镜像清单支持”和“实际运行通过”。仅修改文档时检查链接和命令即可。

## 版本和修订

- 上游版本变化：增加版本目录及对应规格，保留需要继续支持的旧版本。
- 同一上游版本的打包修正：增加 `package_revision`，更新变更记录，镜像版本不冒充升级。
- 标签格式：`<app>-<version>-r<revision>`，例如 `bark-2.4.0-r1`。
- 已发布标签与 Release 不覆盖重写；再修正时使用新的修订号。

首次 r1 的变更已记入 [CHANGELOG.md](CHANGELOG.md)。

## GitHub CI 与发布

推送到 `main` 或创建 PR 时，工作流检查应用包和工具，并运行 Bark 的基本 Docker 测试。手动触发可启用 MySQL；推送发布标签时会增加 MySQL 测试。测试通过且标签与当前规格一致后，构建对应 ZIP、SHA256 并创建 GitHub Release。

只发布已合并到维护分支并验证过的提交。打标签和推送由维护者主动执行，例如：

```bash
git tag -a bark-2.4.0-r1 -m 'Bark 2.4.0 package revision 1'
git push origin bark-2.4.0-r1
```

本地构建无需 GitHub，也不会创建标签或发布：

```bash
python scripts/package.py --tag bark-2.4.0-r1
```

未来增加其他应用时，发布前把它们的实际运行测试加入工作流。当前 CI 的容器测试只覆盖 Bark。
