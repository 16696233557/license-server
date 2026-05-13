# 餐卡系统授权服务端

轻量授权验证服务，用于验证客户端卡密。

## 快速本地测试

```bash
cd license-server
pip install -r requirements.txt
python -m app.main
```

访问 http://localhost:8001/static/admin.html

**默认管理账号**：admin / admin888

## 部署到 Railway（推荐）

1. 注册 [Railway](https://railway.app)（GitHub登录，免费额度够用）
2. New Project → Provision PostgreSQL（可选，SQLite免费够用）
3. New → Empty Service
4. 关联 GitHub 仓库，选择 `license-server` 分支
5. 设置：
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Variables**: 添加 `LICENSE_DB_PATH=/data/license.db`
   - **Persistent Disk**: 开启，Mount Path `/data`
6. 部署完成后访问 `https://xxx.up.railway.app/static/admin.html`

## 部署到 Render

1. GitHub 新建仓库，上传本项目
2. Render → New → Web Service → 关联仓库
3. 设置：
   - Name: `canteen-license`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment: Python 3
4. 添加 Environment Variable：
   - `LICENSE_DB_PATH=/data/license.db`
5. 开启 Persistent Disk，Mount `/data`
6. 访问 `https://canteen-license.onrender.com/static/admin.html`

## 管理后台功能

- 查看所有卡密（状态/到期日）
- 生成新卡密（支持30天/90天/1年/永久）
- 续期（+30天/+90天/+365天）
- 封禁/恢复卡密
- 统计概览

## 客户端验证接口

```
POST /api/verify
  参数: key=卡密&machine_code=机器码
  返回: {"valid": true/false, "message": "...", "expires_at": "2025-01-01"}

GET /api/check
  参数: key=卡密&machine_code=机器码
  返回: {"valid": true/false, "expires_at": "2025-01-01"}
```
