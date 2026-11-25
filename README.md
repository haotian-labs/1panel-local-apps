# 1Panel Local Apps

为 1Panel 本地应用商店维护 Docker 应用安装包。每个包同时核对 1Panel 格式和上游官方部署方式，并记录测试范围与迁移要求。

| 应用 | 上游版本 | 打包修订 | 默认存储 | 验证说明 |
| --- | --- | --- | --- | --- |
| [Bark](apps/bark/) | 2.4.0 | r1 | 本地 Bbolt，可选外部 MySQL | [安装、迁移和测试](docs/apps/bark.md) |

## 安装到 1Panel

1. 获取某个应用的 Release ZIP，或从本仓库的 `apps/` 中复制该应用文件夹。
2. 在 **1Panel 服务器**上放到 `/opt/1panel/resource/apps/local/<应用名>/`。自定义安装根目录时调整路径。
3. 进入应用商店的本地应用页面，更新应用列表，选择版本安装。

Bark 应有 `/opt/1panel/resource/apps/local/bark/data.yml` 和 `bark/2.4.0/docker-compose.yml`，不要多套一层目录。

这是应用商店的资源目录。运行数据由实际安装实例管理；同步仓库和刷新列表不会自动升级已安装实例。已有 Bark 安装请先阅读[迁移说明](docs/apps/bark.md#已有安装迁移)。

## 本地维护

需要 Python 3.10+；Compose 解析和容器测试需要 Docker Compose。容器测试的端口覆盖要求 Compose 2.24.4+。全新 Python 环境中执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python scripts/validate.py --compose
python -m unittest discover -s tests -v
python scripts/package.py bark --version 2.4.0
```

打包生成 `dist/bark-2.4.0-r1.zip` 和 `.zip.sha256`。ZIP 仅包含应用根文件和选定版本，包括默认 `.env` 与 `data/.gitkeep`。

Docker 已运行时执行：

```bash
python scripts/smoke_bark.py
python scripts/smoke_bark.py --mysql
```

测试在 `work/` 中使用临时包副本、独立网络和仅监听本机的端口，结束时清理测试容器与网络。不会使用真实 APNs token；结果保存在 `work/docker-bark.json`。

## 同步到服务器

在服务器克隆仓库并安装 Python 依赖后，先预览，再执行：

```bash
python scripts/sync.py bark
python scripts/sync.py bark --apply
```

自定义安装根目录时增加 `--target /实际根目录/1panel/resource/apps/local`。工具只同步指定应用，替换前把旧资源包备份到相邻的 `local-backups/`；它不会启动容器或迁移实例数据。详细步骤见[部署说明](docs/deployment.md)。

## 仓库约定

- `apps/`：可以导入 1Panel 的应用包，不放真实凭据和运行数据。
- `specs/`：对应版本的官方来源、安装规格和 `package_revision`，用于复核及发布校验。
- `docs/apps/`：应用安装、备份、迁移、来源和测试边界。
- `scripts/`、`tests/`：校验、打包、同步与回归测试。
- `work/`、`dist/`：临时文件、Docker 测试记录和构建产物，均不提交 Git。

`specs/` 保存审核依据，当前工具并不根据它自动重写整个应用包；调整参数时同步修改包、规格和文档。

新增应用与版本发布见 [CONTRIBUTING.md](CONTRIBUTING.md)。原始维护代码采用 MIT；上游软件和图标的来源说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

参考：[1Panel 官方本地应用文档](https://github.com/1Panel-dev/appstore/wiki/How-to-submit-your-own-application)。
