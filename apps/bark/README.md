## 产品介绍

**Bark** 是 Bark iOS 客户端的自托管推送服务端，可通过 HTTP 接口向自己的 iPhone 发送自定义通知。

## 主要功能

- **自定义推送**：支持通过 HTTP GET、POST 和 JSON 请求发送通知。
- **数据存储**：默认使用本地 Bbolt 数据库，也支持连接外部 MySQL。
- **访问认证**：支持可选的 HTTP Basic Auth；上游允许健康检查和设备注册接口免认证访问。
