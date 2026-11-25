# 导入与更新本地应用

## 导入 ZIP

在 1Panel 服务器的文件管理器中打开 `/opt/1panel/resource/apps/local/`，上传应用 ZIP 并解压到当前目录。

以 Bark 为例，元数据必须直接位于 `local/bark/data.yml`，版本文件位于 `local/bark/2.4.0/`。不要将整个 Git 仓库或额外的 ZIP 外层文件夹放在这里。

进入应用商店的本地应用页面，更新列表，再选择应用版本安装。1Panel 自定义安装根目录时需要调整上述路径。

## 从 Git 工作副本同步

把仓库克隆到服务器单独的维护目录。不要在本地应用资源目录或已安装实例目录直接运行 Git 和测试容器。

在服务器安装 Python 3.10+、创建虚拟环境并安装 `requirements.txt` 后，使用：

```bash
python scripts/sync.py bark
python scripts/sync.py bark --apply
```

第一条仅比较新增、修改和删除的文件，不创建目标目录。第二条校验包后应用变更。只替换 `bark`，不会同步或删除其他应用。

默认目标：`/opt/1panel/resource/apps/local`。自定义路径示例：

```bash
python scripts/sync.py bark --target /data/1panel/resource/apps/local
python scripts/sync.py bark --target /data/1panel/resource/apps/local --apply
```

同步需要有目标目录写权限。路径必须以 `resource/apps/local` 结尾，不允许经过符号链接；目标里发现数据库、日志或非空敏感凭据时会停止，避免误覆盖运行目录。

有内容变更时，旧应用资源目录会移动到相邻的 `resource/apps/local-backups/<应用名>-<UTC时间>-<随机后缀>`。新包从临时目录替换进去；替换失败时尝试恢复旧目录。备份由维护者按需清理，不自动删除。

## 更新与回退

同步资源后刷新面板列表。后续是否升级、重建或迁移已安装实例，按具体应用文档操作。

资源包备份只用于恢复商店资源，不包含已安装实例的数据备份。恢复旧资源或切换 Git 提交不会回退已经发生的数据库结构变化。生产更新前，应另行备份实例配置与数据。

同步脚本不会调用 Docker 或面板 API，也不管理服务器上的运行实例。

依据：[1Panel 官方本地应用导入说明](https://github.com/1Panel-dev/appstore/wiki/How-to-submit-your-own-application#6-local-testing)。
