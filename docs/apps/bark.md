# Bark 2.4.0 / r1

Bark 自托管服务端，使用官方 `finab/bark-server:v2.4.0`。本包保留上游入口脚本、默认运行用户、8080 容器端口与数据目录 `/data`。

## 安装参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| HTTP 端口 | 8080 | 宿主机端口，被占用时更换 |
| MySQL DSN | 空 | 留空使用本地 Bbolt；外部数据库仅支持 MySQL，不支持 PostgreSQL |
| Basic Auth 用户名 | 空 | 建议与密码一起填写，或两者同时留空 |
| Basic Auth 密码 | 空 | 仅在表单中遮罩显示，Docker 环境变量仍包含明文值 |

MySQL 不是必需依赖，个人单实例部署可以直接使用 Bbolt。若使用外部 MySQL，先建立数据库和账号并保证网络可达，示例 DSN：

```text
bark:password@tcp(mysql:3306)/bark
```

`mysql` 替换为实际数据库服务名或地址。同一 Docker 网络中的数据库可以使用服务名；`127.0.0.1` 指 Bark 容器自身，不能用于另一个数据库容器。Bark 启动时自动建立所需表结构。

安装目标是 `/opt/1panel/resource/apps/local/bark`；完整导入方法见[部署说明](../deployment.md)。不要在仓库的 `apps/bark/2.4.0` 下直接启动容器。

## 访问与认证

Bark 是 HTTP API 服务，没有管理后台页面。在服务器执行：

```bash
curl http://127.0.0.1:8080/ping
```

返回包含 `"message":"pong"` 的 JSON 表示服务可访问。公网使用时配置域名、HTTPS 及相应访问规则，再在 Bark 客户端添加你的服务地址。

启用 Basic Auth 后，推送工具必须提供凭据。可以让 curl 提示输入密码，避免把密码直接写进命令历史：

```bash
curl --user your-username \
  'https://bark.example.com/YOUR_DEVICE_KEY/test'
```

官方 v2.4.0 对 `/ping`、`/register`、`/healthz` 的路径前缀放行；错误或缺失凭据访问受保护接口返回 HTTP 418。这层验证不代替 HTTPS，也不等于消息端到端加密。

## 持久化与备份

使用 `./data:/data`，每个实际安装实例独立保存 `data/bark.db`。容器重建时应保留该目录。仓库和商店资源包里的 `data/` 只包含 `.gitkeep`，不是生产数据库位置。

直接复制 Bbolt 数据库文件前先停止 Bark，备份实际实例的整个 `data` 目录和必要配置。MySQL 模式按数据库自己的备份流程维护。

上游以 `0600` 创建 `bark.db`，官方容器默认以 root 运行。在 Linux 上，宿主机普通用户不能直接读取该文件；迁移时应使用具有相应读取权限的账号或临时容器，并保留文件权限。仓库测试使用同一官方镜像中的临时 root 容器离线复制，源目录只读挂载，不修改应用的数据权限。

## 已有安装迁移

旧包默认把数据挂载到宿主机 `/home/bark/data`。若实际设置过其他 `BARK_ROOT_PATH`，以已安装实例 `.env` 和容器挂载为准。资源包改为相对目录后，不能把刷新应用列表当作已完成迁移。

1. 备份旧实例配置、数据库和实际挂载信息，停止旧 Bark 容器。
2. 准备新实例，并停止其容器。检查新实例 data 中是否已有需保留的数据；先备份再覆盖。
3. 在新旧容器均停止的状态下，把旧 data 的内容完整复制到新实例实际安装目录下的 data 中。不要复制到商店资源目录或 Git 仓库。
4. 保留原来需要的端口、DSN 和认证设置，启动新实例，验证 `/ping` 与原设备 Key。
5. 确认可用后再移除旧实例。若使用外部 MySQL，保留原数据库、权限和 DSN，无需复制 Bbolt 文件。

本包没有自动生产数据迁移脚本。上游自身的数据库结构处理仍由应用完成，不在包中重复实现。

## 验证记录

最近完成的 arm64 实测记录见 [JSON](../testing/bark-2.4.0-arm64.json)。覆盖默认启动、版本检查、设备注册、重启、停止/启动、容器重建、Basic Auth、多实例隔离、离线数据库迁移和 MySQL。

可在 Docker 已启动的开发机上复测：

```bash
python scripts/smoke_bark.py --mysql
```

官方镜像索引中核实了 `linux/amd64`、`linux/arm64`、`linux/arm/v7`。原生实测为 arm64；GitHub 默认 Linux runner 的实际测试架构以工作流记录为准。不能由清单支持推断每个架构都已运行通过。

测试使用虚拟 token，未验证真实 iPhone 收到 APNs 通知；也没有在运行的 1Panel 服务器完成安装、升级和卸载验收。

## 维护依据

- [官方安装说明](https://github.com/Finb/bark-server/blob/v2.4.0/README.md)
- [官方 Compose](https://github.com/Finb/bark-server/blob/v2.4.0/deploy/docker-compose.yaml)
- [Dockerfile 与默认用户](https://github.com/Finb/bark-server/blob/v2.4.0/deploy/Dockerfile)
- [入口脚本](https://github.com/Finb/bark-server/blob/v2.4.0/deploy/entrypoint.sh)
- [环境变量与数据库选择](https://github.com/Finb/bark-server/blob/v2.4.0/main.go)
- [认证实现](https://github.com/Finb/bark-server/blob/v2.4.0/route_auth.go)
- [MySQL 建表与结构迁移](https://github.com/Finb/bark-server/blob/v2.4.0/database/mysql.go)
- [完整包规格](../../specs/bark/2.4.0.json)

根描述及专有表单文案在非中文语言中使用英文回退；通用端口标签使用已有翻译。第三方图标和许可信息见 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)。
