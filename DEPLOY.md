# 历史回响 Echoes · 部署指南

架构：**后端（会诊引擎 + API）放 Render** · **前端（页面）放 Vercel**。
后端为什么不放 Vercel：会诊一次要 60–90 秒，Vercel 免费函数上限 60 秒会超时；Render 是真实服务器，不受此限。

> 最省事：**只部署 Render 就有完整可用的站**（Render 同时托管页面 + API），
> 地址是 `https://<你的服务名>.onrender.com/echoes`。Vercel 是可选的"更快前端层"。

---

## 一、后端上 Render（必做）

1. 打开 https://render.com → 用 GitHub 登录。
2. **New +** → **Blueprint** → 选中 `echoes` 仓库 → Render 自动读 `render.yaml`。
3. 它会让你填两个密钥（标了 *sync:false* 的）：
   - `OPENAI_API_KEY` = 你的 DeepSeek key（`.env.local` 里那个）
   - `MANIFESTO_API_KEY` = 可留空
4. **Apply / Deploy**。首次构建约 2–4 分钟。
5. 完成后访问 `https://<服务名>.onrender.com/echoes` —— 完整站点已上线。

> 免费档说明：15 分钟无访问会休眠，下次首访冷启动约 30–60 秒（属正常）。

---

## 二、前端上 Vercel（可选，更快的页面层）

前提：先完成第一步，拿到 Render 后端地址（如 `https://echoes-api.onrender.com`）。

1. 编辑 `web/echoes.html` 顶部这一行，把后端地址填进去：
   ```html
   <script>window.ECHOES_CONFIG = { apiBase: "https://echoes-api.onrender.com" };</script>
   ```
   （提交并推送这次改动。）
2. 打开 https://vercel.com → 用 GitHub 登录 → **Add New → Project** → 选 `echoes` 仓库。
3. **Root Directory** 选 `web`；Framework 选 **Other**。
4. **Deploy**。页面上线在 `https://<项目>.vercel.app`。
5. 回 Render 控制台，把 `ALLOWED_ORIGINS` 从 `*` 改成你的 Vercel 域名（收紧跨域），如
   `https://echoes.vercel.app`。

---

## 本地自查

```bash
PYTHONPATH=src .venv/bin/python -m uvicorn hindcast.web:app --port 8000
# 浏览器开 http://127.0.0.1:8000/echoes
```

环境变量见 `.env.example`。
